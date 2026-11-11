with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'rb') as f:
    content = f.read()

# The pattern is: roc_auc\, \N/A\)  (literal backslashes in the source)
# In bytes: roc_auc\\, \\N/A\\)  (each backslash is doubled in Python repr)
content = content.replace(b'roc_auc\\\\, \\\\N/A\\\\)', b'roc_auc, "N/A"')
content = content.replace(b'f1\\\\, \\\\N/A\\\\)', b'f1, "N/A"')

with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'wb') as f:
    f.write(content)

print('Fixed with correct pattern')