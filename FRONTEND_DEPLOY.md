# Deploy AURA Frontend - Simple Web Console Method

Since Firebase CLI isn't installed, here's the **easiest way** to deploy using just your web browser!

## Method: Firebase Hosting via Web Console

### Step 1: Go to Firebase Console
Open: https://console.firebase.google.com/

### Step 2: Select or Create Project
- Click on your existing project `aura-481811`
- OR click "Add project" to create a new one

### Step 3: Enable Hosting
1. In the left menu, click **"Hosting"**
2. Click **"Get started"**

### Step 4: Upload Your File

**Option A: Using Firebase Web Interface**
1. You'll see a deployment area
2. Drag and drop `frontend/index.html` directly into the browser
3. Click **"Deploy"**

**Option B: Enable Web Upload**
1. Go to Hosting settings
2. Look for "Deploy" button
3. Upload your `index.html` file

### Step 5: Get Your URL!
After deployment, you'll get a URL like:
- `https://aura-481811.web.app`
- `https://aura-481811.firebaseapp.com`

---

## Alternative: Even Simpler - Use GitHub Pages

If you have a GitHub account, this is THE EASIEST:

### Step 1: Create a GitHub Repository
1. Go to https://github.com/new
2. Repository name: `AURA`
3. Public
4. Click "Create repository"

### Step 2: Upload Your File
1. In the new repo, click "uploading an existing file"
2. Drag `frontend/index.html`
3. Commit changes

### Step 3: Enable GitHub Pages
1. Go to Settings → Pages (in left menu)
2. Source: "Deploy from a branch"
3. Branch: `main`, Folder: `/` (root)
4. Click Save

### Step 4: Get Your URL!
After a few minutes:
`https://YOUR_USERNAME.github.io/AURA/index.html`

---

## Quickest Solution: I'll Open the Consoles for You

Let me open both Firebase Console and GitHub for you, and you can choose which one to use!
