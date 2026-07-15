import re

path = '/app/app/services/repurposing.py'
content = open(path).read()

old = '''            pred = Prediction(
                drug_id=drug.id,          # always a real int now
                disease_id=disease.id,
                model_version_id=model_version_id,
                prediction_score=res["prediction_score"],
                rank=rank + 1,
                status="pending",
            )
            self.db.add(pred)
            persisted += 1'''

new = '''            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(Prediction).values(
                drug_id=drug.id,
                disease_id=disease.id,
                model_version_id=model_version_id,
                prediction_score=res["prediction_score"],
                rank=rank + 1,
                status="pending",
                version=1,
                is_deleted=False,
            ).on_conflict_do_update(
                constraint="uq_predictions_drug_disease_model",
                set_=dict(
                    prediction_score=res["prediction_score"],
                    rank=rank + 1,
                    status="pending",
                ),
            )
            await self.db.execute(stmt)
            persisted += 1'''

if old in content:
    open(path, 'w').write(content.replace(old, new))
    print("Patched OK")
else:
    print("Pattern not found - already patched or different version")
