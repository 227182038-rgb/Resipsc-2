with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'rb') as f:
    content = f.read()

# Complete replacement of the problematic line
clean_line = b'        LOGGER.info(f"Resipsc V3: AUC={resipsc_metrics.get(\'roc_auc\', \'N/A\')}, F1={resipsc_metrics.get(\'f1\', \'N/A\')}")'

lines = content.split(b'\n')
for i, line in enumerate(lines):
    if b'roc_auc' in line and b'N/A' in line:
        print(f'Replacing line {i}')
        lines[i] = clean_line
        break

new_content = b'\n'.join(lines)
with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'wb') as f:
    f.write(new_content)

print('Replaced line 78 completely')