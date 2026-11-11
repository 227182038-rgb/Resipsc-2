with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'rb') as f:
    content = f.read()

# Fix the problematic line with exact byte replacement
content = content.replace(
    b'roc_auc\\\\\\\\, \\\\N/A\\\\):.4f}, F1={resipsc_metrics.get(\\\\f1\\\\\\\\, \\\\N/A\\\\):.4f}\')',
    b'roc_auc, "N/A":.4f}, F1={resipsc_metrics.get("f1", "N/A"):.4f}\')'
)

# Also try a more direct approach - replace the specific escaped characters
content = content.replace(b'roc_auc\\\\\\\\, \\\\N/A\\\\)', b'roc_auc, "N/A"')
content = content.replace(b'f1\\\\\\\\, \\\\N/A\\\\)', b'f1, "N/A"')

with open(r'E:\resipsc v2 final 1\scripts\run_master_benchmark.py', 'wb') as f:
    f.write(content)

print('Fixed benchmark - second attempt')