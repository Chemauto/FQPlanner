# RoboOS

RoboOS is a robotics operating system featuring a "brain-cerebellum" hierarchical architecture, enabling multi-robot collaboration across different morphologies through Large Language Models.

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Conda
- Redis Server (must be running)

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/FlagOpen/RoboOS.git
cd RoboOS

# Create Conda environment and install dependencies
conda create -n RoboOS python=3.10
conda activate RoboOS
pip install -r requirements.txt

# Install FlagScale dependency
git clone https://github.com/FlagOpen/FlagScale.git
cd FlagScale
# A specific commit might be needed, check RUN.md if you have issues
pip install .
cd ..
```

### 3. Running the System

You can run the system manually or use the deployment UI.

#### Manual Startup (in 3 separate terminals)

1.  **Start Master:**
    ```bash
    # Terminal 1
    conda activate RoboOS
    python master/run.py
    ```
2.  **Start Slaver:**
    ```bash
    # Terminal 2
    conda activate RoboOS
    python slaver/run.py
    ```
3.  **Start Web UI:**
    ```bash
    # Terminal 3
    conda activate RoboOS
    python deploy/run.py
    ```

After starting, the main Web UI is available at `http://127.0.0.1:8888`.

#### Using the Deploy UI (Recommended)

1.  Start the deployment service:
    ```bash
    conda activate RoboOS
    python deploy/run.py
    ```
2.  Open your browser to `http://127.0.0.1:8888`.
3.  Configure and start all services from the web interface. This is the easiest way to get started.

### 4. Publishing a Task

Once the system is running, you can give tasks to the robot.

- **Via the Web UI:** Navigate to the "Publish Task" section.
- **Via Script:** Run the example navigation test script.
  ```bash
  python test_navigation.py
  ```
  Follow the on-screen prompts to send a navigation command like "到垃圾桶前方" (Go to the front of the trash can).

