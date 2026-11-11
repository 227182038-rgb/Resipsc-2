with open(r'E:\resipsc v2 final 1\resipsc\models\scvi_trainer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix escaped triple quotes
content = content.replace('\\"""', '"""')

with open(r'E:\resipsc v2 final 1\resipsc\models\scvi_trainer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed scvi_trainer.py')