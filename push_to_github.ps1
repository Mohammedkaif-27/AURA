# GitHub Push Script for AURA
# Created: 2025-12-21

Write-Host "=== AURA GitHub Push Script ===" -ForegroundColor Cyan
Write-Host ""

# Navigate to project directory
Set-Location C:\Users\mdkai\Desktop\AURA2

# Check git status
Write-Host "Checking git status..." -ForegroundColor Yellow
git status

Write-Host ""
Write-Host "=== Instructions ===" -ForegroundColor Green
Write-Host "1. Go to https://github.com/new" -ForegroundColor White
Write-Host "2. Create repository named: AURA-AI-Chatbot" -ForegroundColor White
Write-Host "3. Set to PRIVATE" -ForegroundColor White
Write-Host "4. Don't initialize with anything" -ForegroundColor White
Write-Host "5. Click 'Create repository'" -ForegroundColor White
Write-Host ""
Write-Host "Press Enter when repository is created..."
Read-Host

# Add remote
Write-Host "Adding GitHub remote..." -ForegroundColor Yellow
git remote add origin https://github.com/Mohammedkaif-27/AURA-AI-Chatbot.git

# Check if remote was added
git remote -v

# Rename branch to main
Write-Host "Renaming branch to main..." -ForegroundColor Yellow
git branch -M main

# Push to GitHub
Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
Write-Host "You'll need to authenticate with GitHub:" -ForegroundColor Cyan
Write-Host "  Username: Mohammedkaif-27" -ForegroundColor White
Write-Host "  Password: Use Personal Access Token (not your GitHub password)" -ForegroundColor White
Write-Host ""
Write-Host "Get token from: https://github.com/settings/tokens" -ForegroundColor White
Write-Host ""

git push -u origin main

# Success message
Write-Host ""
Write-Host "=== Done! ===" -ForegroundColor Green
Write-Host "Repository URL: https://github.com/Mohammedkaif-27/AURA-AI-Chatbot" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. View your repo: https://github.com/Mohammedkaif-27/AURA-AI-Chatbot" -ForegroundColor White
Write-Host "2. Deploy to Google Cloud: gcloud run deploy --source ." -ForegroundColor White
Write-Host ""
