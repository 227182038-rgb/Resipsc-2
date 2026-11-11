with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'rb') as f:
    content = f.read()

# Fix BOM
if content.startswith(b'\xef\xbb\xbf'):
    content = content[3:]

# Fix escaped triple quotes
content = content.replace(b'\\\\"\\\\"\\\\"', b'"""')
content = content.replace(b'\\"\\"\\"', b'"""')

# Fix escaped quotes in f-strings
content = content.replace(b'roc_auc\\\\\\\\, \\\\N/A\\\\\\\\)', b'roc_auc, "N/A"')
content = content.replace(b'f1\\\\\\\\, \\\\N/A\\\\\\\\)', b'f1, "N/A"')

with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'wb') as f:
    f.write(content)

print('Fixed benchmark script')