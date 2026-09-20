-- SLPS-01972 interpreter instrumentation. No writes to emulated memory.
local bit = require('bit')
local ram = PCSX.getMemPtr()
local trace = { enabled = false, rows = 0, limit = 30000, epoch = 0, hooks = {}, returns = {} }
ONETrace = trace
local file = assert(io.open('scenario-trace.jsonl', 'w'))
local function offset(a)
    a = tonumber(a)
    if a >= 0x80000000 and a < 0x80200000 then return a - 0x80000000 end
    error('Trace address outside cached 2 MiB RAM')
end
local function byte(a) return tonumber(ram[offset(a)]) end
local function word(a)
    return byte(a) + byte(a+1)*256 + byte(a+2)*65536 + byte(a+3)*16777216
end
local function hex(a, n)
    local out = {}
    for i=0,n-1 do out[#out+1] = string.format('%02x', byte(a+i)) end
    return table.concat(out)
end
local function quoted(s)
    return '"' .. tostring(s):gsub('[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
local function json(t)
    local parts = {}
    for k,v in pairs(t) do
        parts[#parts+1] = quoted(k)..':'..(type(v)=='string' and quoted(v) or tostring(v))
    end
    table.sort(parts)
    return '{'..table.concat(parts, ',')..'}'
end
local function emit(kind, values)
    if trace.rows >= trace.limit then trace.enabled = false; return end
    trace.rows = trace.rows + 1
    values = values or {}
    values.event, values.sequence, values.epoch = kind, trace.rows, trace.epoch
    values.pc = string.format('%08x', tonumber(PCSX.getRegisters().pc))
    values.cycles = tostring(PCSX.getCPUCycles())
    file:write(json(values)..'\n'); file:flush()
    if trace.rows >= trace.limit then trace.enabled = false end
end
trace.emit = emit
local function scene()
    local s = {}
    for i=0,31 do
        local b = byte(0x800fd230+i)
        if b==0 then break end
        if b<32 or b>126 then return 'unknown' end
        s[#s+1]=string.char(b)
    end
    return table.concat(s)
end
local function state()
    return hex(0x800fa808,32), hex(0x800fa840,20)
end
local function changes()
    local flags, numeric = state()
    if trace.flags and (flags~=trace.flags or numeric~=trace.numeric) then
        emit('state_change', {flags_before=trace.flags, flags_after=flags,
             numeric_before=trace.numeric, numeric_after=numeric,
             interval_after=trace.last or 'start', attribution='between observation points'})
    end
    trace.flags, trace.numeric = flags, numeric
end
local signatures = {
    [0x80018528]=0x90430000, [0x80019a68]=0x8f820978,
    [0x8001a7f8]=0x8f840978, [0x8002a914]=0x3c028007,
    [0x800329e0]=0x27bdffe0, [0x80029c70]=0x0c0168c9,
}
local function validate()
    for a,v in pairs(signatures) do if word(a)~=v then return false end end
    return true
end
local function guarded(callback)
    return function()
        if not trace.enabled then return end
        local ok, err = pcall(callback)
        if not ok then
            emit('trace_error', {message=tostring(err)}); trace.enabled=false
        end
    end
end
local function hook(a, callback)
    trace.hooks[#trace.hooks+1] = PCSX.addBreakpoint(a, 'Exec', 4, 'ONE trace', guarded(callback))
end
local function afterReturn(kind, callback)
    local address = tonumber(PCSX.getRegisters().GPR.n.ra)
    offset(address)
    local epoch = trace.epoch
    if trace.returns[kind] then trace.returns[kind]:remove() end
    trace.returns[kind] = PCSX.addBreakpoint(address, 'Exec', 4, 'ONE trace return', function()
        trace.returns[kind] = nil
        if trace.enabled and trace.epoch==epoch then guarded(callback)() end
        return false
    end)
end
hook(0x80018528, function()
    local g = PCSX.getRegisters().GPR.n
    local p = word(tonumber(g.gp)+0x978)
    if p>=0x10000 then error('Unexpected script position') end
    local op = byte(0x800ea728+p)
    trace.scene, trace.position, trace.opcode = scene(), p, op
    local key = scene()..':'..p..':'..op
    changes()
    if key~=trace.last then
        emit('command', {scene=scene(), offset=p, opcode=op, bytes=hex(0x800ea728+p,8)})
        trace.last = key
    end
    if op==0x11 and trace.choiceTextKey~=key then
        trace.choiceTextKey=key
        local size=0
        while size<4096 and byte(0x800ea729+p+size)~=0 do size=size+1 end
        emit('choice_text', {scene=scene(), offset=p, cp932_hex=hex(0x800ea729+p,size), truncated=size==4096})
    end
    if op==0x20 and trace.choiceKey~=key then
        trace.choiceKey=key
        emit('choice_begin', {scene=scene(), offset=p, variable=byte(0x800ea729+p), count=byte(0x800ea72a+p)})
        trace.choiceCount, trace.choiceVariable = byte(0x800ea72a+p), byte(0x800ea729+p)
        if trace.pauseChoice then trace.atChoice=true; PCSX.pauseEmulator() end
    end
end)
hook(0x80019a68, function()
    local gp=tonumber(PCSX.getRegisters().GPR.n.gp)
    local p=word(gp+0x978)
    local index=byte(0x800ea729+p)
    emit('choice_result', {scene=scene(), offset=p, variable=index, value=byte(0x800fa840+index)})
    changes(); trace.choiceKey=nil; trace.atChoice=false
end)
hook(0x8001a7f8, function()
    local gp=tonumber(PCSX.getRegisters().GPR.n.gp)
    local p=word(gp+0x978)
    local passed=word(gp+0x838)==1
    local target=byte(0x800ea729+p)+256*byte(0x800ea72a+p)
    emit('branch', {scene=scene(), condition_tail=p, passed=passed, next_offset=passed and p+3 or target,
         lhs=word(gp+0x830), rhs=word(gp+0x834), note='lhs/rhs are final comparison of possibly compound condition'})
end)
hook(0x8002a914, function()
    emit('snapshot_begin', {scene=scene()})
    afterReturn('snapshot', function()
        local sum=0
        for i=0,108 do sum=sum+byte(0x801b3110+i) end
        emit('snapshot_ready', {record_hex=hex(0x801b3110,128), checksum_calculated=sum%65536,
              checksum_stored=byte(0x801b318c)+256*byte(0x801b318d)})
    end)
end)
hook(0x800329e0, function()
    emit('restore_begin', {record_hex=hex(0x80079af8,128)})
    afterReturn('restore', function() changes(); emit('restore_return', {scene=scene()}) end)
end)
hook(0x80029c70, function()
    local g=PCSX.getRegisters().GPR.n
    emit('card_call', {a0=tonumber(g.a0), a1=tonumber(g.a1), a2=tonumber(g.a2), a3=tonumber(g.a3),
          record_hex=hex(tonumber(g.a2),128), scope='game-side transfer; card completion not inferred'})
    afterReturn('card', function() emit('card_call_return', {v0=tonumber(PCSX.getRegisters().GPR.n.v0)}) end)
end)
-- BIOS file-I/O boundaries; captures arguments, not inferred completion.
for _, entry in ipairs({{0x000000a0,'A0',0x00,0x04},{0x000000b0,'B0',0x32,0x36}}) do
    local address, name, first, last = entry[1], entry[2], entry[3], entry[4]
    hook(address, function()
        local g=PCSX.getRegisters().GPR.n
        local fn=bit.band(tonumber(g.t1),255)
        if fn>=first and fn<=last then
            emit('bios_io', {table=name, fn=fn, ra=tonumber(g.ra), a0=tonumber(g.a0),
                 a1=tonumber(g.a1), a2=tonumber(g.a2), a3=tonumber(g.a3)})
        end
    end)
end
PCSX.WebServer.Handlers['one-trace'] = function(request)
    if request.method~='POST' then return 'HTTP/1.1 405 Method Not Allowed\r\n\r\n' end
    local query={}
    for k,v in (request.urlData.query or ''):gmatch('([%w_]+)=([%w_]+)') do query[k]=v end
    if query.action=='stop' then trace.enabled=false; emit('stop'); return json({enabled=false}) end
    if query.action~='start' then return 'HTTP/1.1 400 Bad Request\r\n\r\nInvalid action' end
    if not validate() then return 'HTTP/1.1 409 Conflict\r\n\r\nSLPS-01972 code signatures do not match; load game first' end
    if trace.rows>=trace.limit then return 'HTTP/1.1 409 Conflict\r\n\r\nTrace limit reached; restart observer' end
    for _,bp in pairs(trace.returns) do bp:remove() end
    trace.returns={}; trace.epoch=trace.epoch+1; trace.last=nil; trace.choiceKey=nil; trace.choiceTextKey=nil
    trace.flags,trace.numeric=state()
    trace.atChoice=false; trace.choiceCount=0; trace.choiceVariable=0
    trace.pauseChoice=query.pause_choice=='1'; trace.enabled=true
    emit('start', {flags=trace.flags, numeric=trace.numeric, profile='SLPS-01972'})
    return json({enabled=true, epoch=trace.epoch})
end
PCSX.WebServer.Handlers['one-trace-status'] = function()
    return json({enabled=trace.enabled, rows=trace.rows, limit=trace.limit, epoch=trace.epoch,
        at_choice=trace.atChoice or false, choice_count=trace.choiceCount or 0,
        choice_variable=trace.choiceVariable or 0, scene=trace.scene or '',
        offset=trace.position or -1, opcode=trace.opcode or -1})
end
print('ONE scenario trace ready; enable after game load with POST one-trace?action=start')
