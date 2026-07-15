path = '/app/app/services/repurposing.py'
content = open(path).read()

old = '            pred = Prediction(\n                drug_id=drug.id,\n                disease_id=disease.id,\n                model_version_id=model_version_id,\n                prediction_score=res["prediction_score"],\n                rank=rank + 1,\n                status="pending",\n            )\n            self.db.add(pred)\n            persisted += 1'

new = '            from sqlalchemy.dialects.postgresql import insert as pg_insert\n            stmt = pg_insert(Prediction).values(\n                drug_id=drug.id,\n                disease_id=disease.id,\n                model_version_id=model_version_id,\n                prediction_score=res["prediction_score"],\n                rank=rank + 1,\n                status="pending",\n                version=1,\n                is_deleted=False,\n            ).on_conflict_do_update(\n                constraint="uq_predictions_drug_disease_model",\n                set_=dict(\n                    prediction_score=res["prediction_score"],\n                    rank=rank + 1,\n                    status="pending",\n                ),\n            )\n            await self.db.execute(stmt)\n            persisted += 1'

if old in content:
    open(path, "w").write(content.replace(old, new))
    print("Patched OK")
else:
    print("Not found")
