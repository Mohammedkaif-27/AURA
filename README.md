# AURA2 - Customer Support Agent

## Setup

1.  **Install Dependencies**
    Ensure you have Python installed. Run the following command in the project root:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration**
    Ensure you have a `.env` file in the root directory with your API key:
    ```env
    GOOGLE_API_KEY=your_api_key_here
    ```

## Running the Application

You need to run the backend and frontend in separate terminals.

### 1. Start Support Backend
Open a terminal and run:
```bash
uvicorn backend.main:app --reload
```
The backend will start at `http://127.0.0.1:8000`.

### 2. Start User Frontend
Open a **new** terminal and run:
```bash
streamlit run frontend/app.py
```
The frontend will open in your browser (usually at `http://localhost:8501`).

## Troubleshooting
- **Backend fails to start**: Check if `GOOGLE_API_KEY` is set in `.env` and all dependencies are installed.
- **Frontend can't connect**: Ensure the backend is running on port 8000.
