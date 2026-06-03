#!/usr/bin/env python3
content = open('cb_noredeem_strategy_v2.py').read()

# Fix 1: print() for bonds count -> writer.write()
old = "    print('  全量: ' + str(len(bonds)) + ' 只')"
new = "    writer.write('  全量: ' + str(len(bonds)) + ' 只\\n')"
content = content.replace(old, new)

# Fix 2: print for bad rating exclusion -> writer.write()
old = "            print(f'  排除 {detail[\"name\"]}({bid}) 评级{rating_v} 不合格')"
new = "            writer.write(f'  排除 {detail[\"name\"]}({bid}) 评级{rating_v} 不合格\\n')"
content = content.replace(old, new)

# Fix 3: print( for session before bonds (already replaced in fix 1 but check)
old = "    print('  全量: ' + str(len(bonds)) + ' 只')\n\n    today_dt = dt.datetime.now()"
new = "    writer.write('  全量: ' + str(len(bonds)) + ' 只\\n')\n    today_dt = now_dt"
content = content.replace(old, new)

# Fix 4: print( for dingtalk response -> writer.write()
old = "    print('[DingTalk] ' + str(resp))"
new = "    writer.write('[DingTalk] ' + str(resp) + '\\n')"
content = content.replace(old, new)

open('cb_noredeem_strategy_v2.py', 'w').write(content)

# Verify
c = open('cb_noredeem_strategy_v2.py').read()
remaining = [line for line in c.split('\n') if "print('" in line or 'print(f' in line]
print(f'Remaining print lines: {len(remaining)}')
for line in remaining[:10]:
    print(' ', line.strip())
print(f'writer.write lines: {c.count(\"writer.write\")}')