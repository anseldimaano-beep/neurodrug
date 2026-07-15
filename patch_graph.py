path = '/app/app/services/graph_service.py'
c = open(path).read()
old = '"id":         disease_efo_id,'
new = '"id":         f"Disease:{disease_efo_id}",'
if old in c:
    c = c.replace(old, new)
    open(path, 'w').write(c)
    print('patched')
else:
    print('pattern not found - showing context:')
    for i,line in enumerate(c.splitlines()):
        if 'disease_efo_id' in line and 'id' in line:
            print(i, repr(line))
