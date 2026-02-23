import re

with open('migrations/versions/021_carrier_agent_tables.py', 'r') as f:
    content = f.read()

# Replace down_revision with '020_pbx_agent_tables'
content = re.sub(r"down_revision = .*", "down_revision = '020_pbx_agent_tables'", content)
content = re.sub(r"revision = .*", "revision = '021_carrier_agent_tables'", content)

lines = content.split('\n')
new_lines = []
in_irrelevant_create = False
paren_count = 0

for line in lines:
    if line.strip().startswith('op.create_table('):
        if not ('carrier_' in line):
            in_irrelevant_create = True
            paren_count = line.count('(') - line.count(')')
            continue
    if in_irrelevant_create:
        paren_count += line.count('(') - line.count(')')
        if paren_count <= 0:
            in_irrelevant_create = False
        continue

    if line.strip().startswith('op.create_index(') and 'carrier_' not in line:
        continue
    if line.strip().startswith('op.drop_index(') and 'carrier_' not in line:
        continue
    if line.strip().startswith('op.drop_table(') and 'carrier_' not in line:
        continue

    new_lines.append(line)

with open('migrations/versions/021_carrier_agent_tables.py', 'w') as f:
    f.write('\n'.join(new_lines))
