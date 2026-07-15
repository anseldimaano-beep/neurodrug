content = open('/app/app/services/etl/orchestrator.py').read()
old = "molecular_weight=mol.get(\"molecule_properties\", {}).get(\"full_mwt\"),"
new = "molecular_weight=float(mwt) if (mwt := mol.get(\"molecule_properties\", {}).get(\"full_mwt\")) else None,"
if old in content:
    open('/app/app/services/etl/orchestrator.py', 'w').write(content.replace(old, new))
    print("Patched OK")
else:
    print("Already patched or pattern not found")
