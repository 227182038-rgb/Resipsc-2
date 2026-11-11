with open(r'E:\resipsc v2 final 1\resipsc\models\scvi_trainer.py', 'rb') as f:
    content = f.read()

# Replace the literal bytes for escaped triple quotes
content = content.replace(b'\\\\"\\\\"\\\\"', b'"""')
content = content.replace(b'\\"\\"\\"', b'"""')

with open(r'E:\resipsc v2 final 1\resipsc\models\scvi_trainer.py', 'wb') as f:
    f.write(content)

print('Fixed scvi_trainer.py bytes')