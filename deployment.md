# Deployment Configuration
project_name=my-app
language=node
port=3000
process_manager=pm2
health_check=/health
deployment_timeout=60
rollback_enabled=true
max_releases=5
ssl=caddy
domain=myapp.example.com

## Start Command
```bash
npm run prod
```
