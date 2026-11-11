with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'rb') as f:
    content = f.read()

lines = content.split(b'\n')
for i, line in enumerate(lines):
    if b'roc_auc' in line and b'N/A' in line:
        print(f'Line {i} before: {line}')
        # Replace the specific escaped sequences
        new_line = line.replace(b'roc_auc\\\\\\\\, \\\\N/A\\\\)', b'roc_auc, "N/A"')
        new_line = new_line.replace(b'f1\\\\\\\\, \\\\N/A\\\\)', b'f1, "N/A"')
        print(f'Fixed line {i}: {new_line}')
        lines[i] = new_line
        break

new_content = b'\n'.join(lines)
with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'wb') as f:
    f.write(new_content)

print('Fixed benchmark directly')