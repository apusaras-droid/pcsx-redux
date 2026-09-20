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
