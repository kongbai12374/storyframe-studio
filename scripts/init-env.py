"""Initialize stable local secrets once; never overwrite an existing environment."""
from pathlib import Path
import secrets
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parent.parent
target=root/'.env'
if target.exists():
 print('Existing .env kept unchanged.')
else:
 content='SECRET_KEY='+secrets.token_hex(32)+'\nENCRYPTION_KEY='+Fernet.generate_key().decode()+'\nADMIN_PASSWORD='+secrets.token_urlsafe(20)+'\nDATA_DIR='+str(root/'runtime')+'\nHOST_METRICS='+str(root/'metrics/host-metrics.json')+'\nALLOWED_HOSTS=localhost,127.0.0.1\nCSRF_TRUSTED_ORIGINS=http://localhost:8010,http://127.0.0.1:8010\n'
 with target.open('x') as f:f.write(content)
 target.chmod(0o600)
 print('Created private .env. Store its stable keys separately before deploying.')
