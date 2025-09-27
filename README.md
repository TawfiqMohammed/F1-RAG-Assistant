# 🏎️ F1 RAG Assistant

A **Formula 1 Retrieval-Augmented Generation (RAG) System** built for speed, accuracy, and simplicity. It features advanced **hybrid search**, seamless integration with local Large Language Models (LLMs) via **LM Studio**, and a sleek, F1-themed web interface.

https://github.com/user-attachments/assets/b3593bfd-42fd-45b9-87a3-e6754ef23e9b

---

## ✨ Features

- 🔍 **Hybrid Search**: Combines **Vector Embeddings** (Sentence-Transformers: `all-MiniLM-L6-v2`) and **BM25** for optimal, high-recall document retrieval.
- 🏁 **Comprehensive F1 Data**: Covers drivers, constructors, races, and championships from **1950 to 2024** (861 drivers, 212 teams, 1,100+ races).
- 🎨 **Modern UI**: F1-inspired, single-page web interface with real-time chat, a session history tracker, and responsive design.
- 📂 **Session Management**: Tracks conversations by session, allowing users to review and repeat past queries.
- 📊 **System Analytics**: Provides real-time metrics on response time, LLM confidence, and query type statistics.
- ⚡ **Production-Ready**: Utilizes a robust architecture with a **SQLite database** for persistent storage, comprehensive error handling, and structured logging.

---

## 🖼️ Screenshots & Demo

A picture is worth a thousand words—showcasing the application's sleek F1-themed design and core functionality.

| Feature | Description | Screenshot/GIF |
| :--- | :--- | :--- |
| **Main Chat Interface** | The primary user interface for asking F1 questions. | <img width="400" alt="System-Home" src="https://github.com/user-attachments/assets/9105c7c6-8908-4f69-ab1e-e005ddbaae89" /> |
| **Search & Response** | A view showing a detailed answer, confidence score, and response time. | <img width="400" alt="System-Query" src="https://github.com/user-attachments/assets/592d307d-2cfc-41b6-86e2-1d7f7e275716" /> |
| **System Statistics** | A snapshot of the `Stats` tab showing system health and data coverage. | <img width="400" alt="System-Status" src="https://github.com/user-attachments/assets/4d302f3f-2166-4042-935f-80796ce18de7" /> |
| **Conversation History**| A tab displaying past queries for the current session. | <img width="400" alt="System-History" src="https://github.com/user-attachments/assets/055d05dc-a509-4897-99e6-b22772d46484" /> |


## 🚀 Quick Start

Follow these steps to get the F1 RAG Knowledge Assistant running locally.

### 1. Project Setup

Clone the repository and install the required dependencies:

```bash
# Clone the repository
git clone <YOUR_REPO_URL>
cd f1-rag-assistant

# Install dependencies
pip install -r requirements.txt
````

### 2\. Add Data

The system works best with comprehensive F1 data.

1.  Download the necessary CSV files (e.g., `drivers.csv`, `races.csv`, `results.csv`, etc.). Sources like the Ergast API or Kaggle datasets are recommended.
2.  Place these files inside the **`data/`** directory.

### 3\. Run the LLM Server (LM Studio)

The RAG system is designed to use a local LLM API for zero-cost, private inference.

1.  **Download and install [LM Studio](https://lmstudio.ai/).**
2.  Load a suitable model.
      * **Recommended Model:** `llama-3.2-3b-instruct` (Configured in `config.py`)
3.  Navigate to the **Local Inference Server** tab and start the server.
4.  Ensure it is running on the default host and port: `http://localhost:1234`.

### 4\. Start the Application

Execute the main Flask application file:

```bash
python app.py
```

### 5\. Access the UI

Open your web browser and navigate to the application frontend:

👉 **http://localhost:5000**

-----

## 🏗️ Architecture

The system uses a clean, modular structure, consolidating core logic into four main files for maximum clarity and maintainability.

```bash
f1-rag-assistant/
├── app.py           # Main Flask application, routing, and server logic.
├── f1_rag.py        # Complete RAG system (Hybrid Search, LLM integration, DB Manager).
├── config.py        # Centralized configuration (LLM URL, Ports, Thresholds).
├── index.html       # Single-page frontend (HTML, Tailwind CSS, JavaScript).
├── data/            # F1 CSV dataset
├── logs/            # System logs
├── f1_rag.db        # SQLite database
└── README.md
```

The data flow follows a standard RAG pattern:

```markdown
┌───────────────┐     ┌─────────────┐     ┌────────────────┐
│   Frontend    │────▶│   Flask API │────▶│   F1 RAG Core  │
│ - Chat UI     │     │ - Endpoints │     │ - Hybrid Search│
│ - History     │     │ - Sessions  │     │ - LLM + Vector │
└───────────────┘     └─────────────┘     └────────────────┘
           ^                 │                   │
           └─────────────────┴───────────────────┘
                           ▼
                   ┌────────────────┐
                   │   SQLite DB    │
                   │  Drivers, Races│
                   │  Logs, Stats   │
                   └────────────────┘
```

-----

## ⚙️ Configuration

All major settings are managed centrally in **`config.py`** and can be overridden using environment variables.

| Setting | Default Value | Description |
| :--- | :--- | :--- |
| **`LLM_URL`** | `"http://localhost:1234"` | Address of the local LM Studio LLM inference server. |
| **`LLM_MODEL`** | `"llama-3.2-3b-instruct"` | Model used for generation. |
| **`DATABASE_PATH`** | `"f1_rag.db"` | Path to the SQLite database file. |
| **`DATA_PATH`** | `"./data"` | Directory for F1 data CSV files. |
| **`TOP_K_RETRIEVAL`** | `8` | Number of documents retrieved by the Hybrid Search. |
| **`CONFIDENCE_THRESHOLD`** | `0.3` | Minimum confidence score for a definitive answer. |
| **`PORT`** | `5000` | Port the Flask application runs on. |

-----

## 💡 Sample Queries

Try these example questions in the UI:

| Category | Example Queries |
| :--- | :--- |
| 🏆 **Championships** | "Who won the 2021 F1 championship?" |
| 👨‍🏎️ **Driver Stats** | "How many wins does Ayrton Senna have?" |
| 🏎️ **Teams** | "Who drives for Ferrari?" |
| 📅 **Races** | "Who won the last Italian GP?" |
| 🧠 **Current Info** | "Current Red Bull drivers" |

-----

## 🛠️ API Endpoints

The Flask application exposes a RESTful API for all core functionality.

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the main frontend application (`index.html`). |
| `/api/query` | `POST` | The main RAG endpoint for asking a question. |
| `/api/health` | `GET` | Returns system health status (DB, LLM connection). |
| `/api/stats` | `GET` | Returns system statistics and data coverage. |
| `/api/session/{id}/history` | `GET` | Retrieves the query history for a specific session ID. |
| `/api/session/{id}/clear` | `POST` | Clears the query history for a specific session ID. |
| `/api/sample-questions` | `GET` | Returns the list of example queries. |

-----

## 🤝 Contributing

Contributions are welcome\! Please keep the core design philosophy in mind: **Keep it simple, keep it fast.**

1.  **Fork** the repository.
2.  Create your feature branch (`git checkout -b feature/AmazingFeature`).
3.  Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4.  Push to the branch (`git push origin feature/AmazingFeature`).
5.  Open a **Pull Request**.
## 📄 License

Distributed under the **MIT License**. See the `LICENSE` file for more information.
