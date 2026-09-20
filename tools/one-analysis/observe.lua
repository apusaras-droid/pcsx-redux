-- Run with PCSX-Redux -interpreter -debugger -dofile <this file>.
-- Output is local to the emulator working directory; game/BIOS bytes are never changed.
local bit = require('bit')
ONEObserver = { enabled = true, count = 0, limit = 20000, counts = {}, breakpoints = {} }
local obs = ONEObserver
local output = assert(io.open('bios-calls.csv', 'w'))
output:write('sequence,table,function,pc,ra,a0,a1,a2,a3\n')
local function hook(name)
    return function()
        if not obs.enabled or obs.count >= obs.limit then return end
        local regs = PCSX.getRegisters()
        local gpr = regs.GPR.n
        local fn = bit.band(tonumber(gpr.t1), 255)
        local key = name .. string.format('%02x', fn)
        obs.counts[key] = (obs.counts[key] or 0) + 1
        -- Bound noisy calls individually, while keeping aggregate counts.
        if obs.counts[key] > 128 then return end
        obs.count = obs.count + 1
        output:write(string.format('%d,%s,%02x,%08x,%08x,%08x,%08x,%08x,%08x\n',
            obs.count, name, fn, tonumber(regs.pc), tonumber(gpr.ra),
            tonumber(gpr.a0), tonumber(gpr.a1), tonumber(gpr.a2), tonumber(gpr.a3)))
        output:flush()
    end
end
for _, entry in ipairs({{'A0', 0xa0}, {'B0', 0xb0}, {'C0', 0xc0}}) do
    local callback = hook(entry[1])
    table.insert(obs.breakpoints, PCSX.addBreakpoint(entry[2], 'Exec', 4, 'ONE BIOS ' .. entry[1], function()
        local ok, err = pcall(callback)
        if not ok then obs.enabled = false; print('ONE observer disabled: ' .. tostring(err)) end
    end))
end
PCSX.WebServer = PCSX.WebServer or {}
PCSX.WebServer.Handlers = PCSX.WebServer.Handlers or {}
local handlers = PCSX.WebServer.Handlers
handlers['one-status'] = function()
    output:flush()
    local regs = PCSX.getRegisters()
    local counts = {}
    for key, value in pairs(obs.counts) do counts[#counts + 1] = string.format('"%s":%d', key, value) end
    table.sort(counts)
    return string.format('{"enabled":%s,"rows":%d,"limit":%d,"pc":"%08x","ra":"%08x","counts":{%s}}',
        tostring(obs.enabled), obs.count, obs.limit, tonumber(regs.pc), tonumber(regs.GPR.n.ra), table.concat(counts, ','))
end
handlers['one-pad'] = function(request)
    if request.method ~= 'POST' then return 'HTTP/1.1 405 Method Not Allowed\r\n\r\n' end
    local query = {}
    for key, value in (request.urlData.query or ''):gmatch('([%w_]+)=([%w_]+)') do query[key] = value end
    local button = PCSX.CONSTS.PAD.BUTTON[query.button or '']
    if button == nil or (query.pressed ~= '0' and query.pressed ~= '1') then
        return 'HTTP/1.1 400 Bad Request\r\n\r\nInvalid button/pressed value'
    end
    local pad = PCSX.SIO0.slots[1].pads[1]
    if query.pressed == '1' then pad.setOverride(button) else pad.clearOverride(button) end
    return '{"ok":true}'
end
print('ONE observer ready: BIOS entry calls only; per-function cap=128, total cap=20000')

-- Narrow RAM watches for following scenario reads and text buffer writes.
local watch = { count = 0, limit = 512 }
local watchOutput = assert(io.open('memory-watch.csv', 'w'))
watchOutput:write('sequence,pc,address,width,ra,v0,a0,a1,a2,a3,s0,s1,s2,s3,t0,t1,t2,t3\n')
handlers['one-watch'] = function(request)
    if request.method ~= 'POST' then return 'HTTP/1.1 405 Method Not Allowed\r\n\r\n' end
    local query = {}
    for key, value in (request.urlData.query or ''):gmatch('([%w_]+)=([%w_]+)') do query[key] = value end
    local address, width = tonumber(query.address or '', 16), tonumber(query.width or '')
    local kind = query.type
    if not address or not width or width < 1 or width > 4096 or width ~= math.floor(width)
       or address < 0x80010000 or address + width > 0x80200000
       or (kind ~= 'Read' and kind ~= 'Write' and kind ~= 'Exec') then
        return 'HTTP/1.1 400 Bad Request\r\n\r\nInvalid RAM watch'
    end
    if watch.breakpoint then watch.breakpoint:remove() end
    watch.count = 0
    watchOutput:write(string.format('# watch,%s,%08x,%d\n', kind, address, width))
    watchOutput:flush()
    watch.breakpoint = PCSX.addBreakpoint(address, kind, width, 'ONE scenario watch', function(access, accessWidth)
        if watch.count >= watch.limit then return false end
        local regs = PCSX.getRegisters()
        local g = regs.GPR.n
        local ok, err = pcall(function()
            watch.count = watch.count + 1
            watchOutput:write(string.format('%d,%08x,%08x,%d,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x,%08x\n',
                watch.count, tonumber(regs.pc), access, accessWidth, tonumber(g.ra), tonumber(g.v0),
                tonumber(g.a0), tonumber(g.a1), tonumber(g.a2), tonumber(g.a3),
                tonumber(g.s0), tonumber(g.s1), tonumber(g.s2), tonumber(g.s3),
                tonumber(g.t0), tonumber(g.t1), tonumber(g.t2), tonumber(g.t3)))
            watchOutput:flush()
        end)
        if not ok then print('ONE watch failed: ' .. tostring(err)); return false end
        if watch.count >= watch.limit then return false end
    end)
    return '{"ok":true,"limit":512}'
end
handlers['one-watch-status'] = function()
    watchOutput:flush()
    return string.format('{"events":%d,"limit":%d}', watch.count, watch.limit)
end
