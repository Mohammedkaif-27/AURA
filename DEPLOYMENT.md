# AURA Backend - Google Cloud Run Deployment Guide

## Prerequisites

1. **Google Cloud CLI installed**
   ```bash
   # Verify gcloud is installed
   gcloud --version
   ```

2. **Authenticated with Google Cloud**
   ```bash
   gcloud auth login
   ```

3. **Set your project**
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   ```

## Required Environment Variables

Before deploying, gather these values:

- **PROJECT_ID**: Your Google Cloud project ID (e.g., `my-project-123456`)
- **REGION**: Deployment region (default: `asia-south1`)
- **SMTP_USERNAME**: Your Gmail/SMTP username for email notifications
- **SMTP_PASSWORD**: Gmail app password (not regular password)
- **SENDER_EMAIL**: Email address for sending notifications

## Deployment Steps

### 1. Enable Required APIs

```bash
gcloud services enable run.googleapis.com
gcloud services enable aiplatform.googleapis.com
```

### 2. Deploy to Cloud Run

Replace the placeholder values with your actual credentials:

```bash
gcloud run deploy aura-backend \
  --source . \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars PROJECT_ID=YOUR_PROJECT_ID,REGION=asia-south1,SMTP_HOST=smtp.gmail.com,SMTP_PORT=587,SMTP_USERNAME=YOUR_EMAIL,SMTP_PASSWORD=YOUR_APP_PASSWORD,SENDER_EMAIL=YOUR_EMAIL
```

**Important Notes:**
- Cloud Run will build from the Dockerfile automatically
- The deployment uses Workload Identity for authentication (no service account JSON needed)
- First deployment may take 3-5 minutes

### 3. Get Your Cloud Run URL

```bash
gcloud run services describe aura-backend --region asia-south1 --format 'value(status.url)'
```

Save this URL - this is your backend API endpoint.

### 4. Test the Deployment

```bash
# Set the URL variable
CLOUD_RUN_URL=$(gcloud run services describe aura-backend --region asia-south1 --format 'value(status.url)')

# Test health endpoint
curl $CLOUD_RUN_URL/health

# Expected output:
# {"status":"ok","service":"AURA Backend","version":"1.0.0"}
```

### 5. Test Chat Endpoint

```bash
# Test chat functionality
curl -X POST $CLOUD_RUN_URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, I need help with my order", "session_id": "test-session"}'

# Should return a JSON response with AURA's reply
```

## Post-Deployment

### View Logs

```bash
gcloud run services logs read aura-backend --region asia-south1 --limit 50
```

### Update Environment Variables

```bash
gcloud run services update aura-backend \
  --region asia-south1 \
  --update-env-vars KEY=VALUE
```

### Redeploy After Code Changes

Simply run the deployment command again:

```bash
gcloud run deploy aura-backend \
  --source . \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated
```

## Troubleshooting

### Build Fails
- Check Dockerfile syntax
- Verify requirements.txt has all dependencies
- Check logs: `gcloud builds list --limit 5`

### Service Crashes
- Check logs: `gcloud run services logs read aura-backend --region asia-south1`
- Verify PROJECT_ID is set correctly
- Ensure REGION matches your Vertex AI region

### Vertex AI Errors
- Verify `aiplatform.googleapis.com` API is enabled
- Check that PROJECT_ID is correct
- Ensure Cloud Run service account has Vertex AI permissions:
  ```bash
  gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
    --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/aiplatform.user"
  ```

### Email Not Sending
- Verify SMTP credentials are correct
- Use Gmail App Password (not regular password)
- Check sender email matches SMTP username

## Cost Considerations

Cloud Run pricing is based on:
- **CPU allocation**: Only charged when processing requests
- **Memory**: 512MB-1GB recommended
- **Requests**: First 2 million requests free per month
- **Vertex AI**: Gemini 2.0 Flash charged per 1000 characters

**Estimated monthly cost for light usage**: $5-20

## Security Best Practices

1. **Restrict Public Access** (Optional)
   ```bash
   gcloud run services update aura-backend \
     --region asia-south1 \
     --no-allow-unauthenticated
   ```

2. **Use Secret Manager** for sensitive env vars:
   ```bash
   # Store SMTP password in Secret Manager
   echo -n "YOUR_SMTP_PASSWORD" | gcloud secrets create smtp-password --data-file=-
   
   # Reference in Cloud Run
   gcloud run services update aura-backend \
     --region asia-south1 \
     --update-secrets SMTP_PASSWORD=smtp-password:latest
   ```

3. **Set Up Custom Domain**
   - Map a custom domain in Cloud Run console
   - Automatically provisions SSL certificate

## Support

For issues:
1. Check Cloud Run logs first
2. Verify all environment variables are set
3. Test locally with Docker before deploying
4. Review implementation_plan.md for architecture details
