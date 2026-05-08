# Claude Code Instructions

## Git Workflow
- Always work directly on the main branch
- Never create new branches
- Before every commit, run: git checkout main
- After every task that modifies files, automatically: git add . && git commit -m "update: [description]" && git push origin main

## Auto-deploy
This project is connected to Render. Every push to main triggers automatic redeployment.
