**Phase 1: Foundation, Testing, and Basic Refactoring**

1.  **Setup Project Structure & Tooling:** ✅
    *   Create a `requirements.txt` file listing all Python dependencies (`evolutionapi`, `pypdf`, `Pillow`, `python-dotenv`, etc.).
    *   Initialize `git` if not already done. Create a .gitignore file.
    *   Set up a testing framework: `pip install pytest pytest-cov`
    *   Configure `pytest` (e.g., create a `pytest.ini` file).
    *   Set up linting and formatting: `pip install flake8 black mypy`
    *   Configure `flake8`, `black`, and `mypy` (e.g., in `pyproject.toml` or `.flake8`, `mypy.ini`).
    *   (Optional) Set up pre-commit hooks to automate checks: `pip install pre-commit && pre-commit install`

2.  **Implement Basic Unit Tests:** ✅
    *   Create a `tests/` directory.
    *   Write unit tests for file_utils.py.
    *   Write unit tests for parsing logic within workflows (e.g., `SplitWorkflow.parse_page_ranges`). Mock file system interactions where necessary.
    *   Run tests and check coverage: `pytest --cov=.`

3.  **Add Type Hinting:** ✅
    *   Incrementally add type hints to function signatures and key variables in utils, config, and workflow files.
    *   Run `mypy .` periodically to check types. Start with less complex modules.

4.  **Define Custom Exceptions:** ✅
    *   Create an `app/exceptions.py` file.
    *   Define base exceptions like `DocumentScannerError` and specific ones like `WorkflowError`, `ExternalToolError`, `ApiError`, `ConfigurationError`.

5.  **Improve Logging:** ✅
    *   Ensure consistent use of logging levels.
    *   Add `task_id` and `sender_jid` to log messages within `WorkflowManager` and workflow methods for better traceability.
    *   Consider configuring logging for a structured format (e.g., JSON) later, but ensure context is present now.

6.  **Refactor External Tool Calls (Initial Pass):** ✅
    *   Create `utils/external_tools.py`.
    *   Create wrapper functions for `subprocess.run` calls (e.g., `run_command`).
    *   Inside wrappers, add basic checks for `returncode != 0` and raise a generic `ExternalToolError` with command and stderr details. Add basic `timeout` arguments. Log the command being run.
    *   Replace direct `subprocess.run` calls in workflows with calls to these wrappers.

7.  **Refactor Workflow Management (Initial Pass):** ✅
    *   Define a `BaseWorkflow` abstract base class (using `abc` module) or a `Protocol` in `workflows/base.py`. Define common method signatures like `handle_file_save`, `handle_command`, `finalize`, `get_instructions`.
    *   Modify existing workflow classes (`MergeWorkflow`, etc.) to nominally inherit/implement this base, even if the implementation still uses static methods for now.
    *   Refactor `WorkflowManager.handle_message` slightly to reduce nesting, perhaps by creating helper methods for different message types (command, file, text).

8.  **Add Basic Integration Tests:** ✅
    *   Write integration tests for `WorkflowManager`, mocking `WhatsAppClient` and the actual processing logic within workflow methods (e.g., assert the correct workflow method is called).
    *   Write basic tests for `WhatsAppClient`, mocking the underlying `evolutionapi` library calls.

**Phase 2: Reliability and Core Architecture**

9.  **Implement Persistent Workflow State:** ✅
    *   Choose a persistence mechanism (Redis recommended for simplicity/performance, SQLite for single-instance ease).
    *   Install necessary client library (e.g., `redis-py`, `sqlalchemy`).
    *   Define how workflow state will be stored (e.g., Redis Hash per `sender_jid` storing JSON).
    *   Modify `WorkflowManager`:
        *   On receiving a message, attempt to load state for the `sender_jid`.
        *   Replace `active_workflows` dictionary with reads/writes to the persistent store.
        *   Ensure state is saved/updated after key actions (workflow start, file received, command processed, task end).
        *   Implement error handling for persistence layer interactions.
        *   Add a TTL or cleanup mechanism for stale states.

10. **Refactor Workflows to Object-Oriented Instances:** ✅
    *   Modify `BaseWorkflow` to include instance attributes (`task_id`, `task_dir`, `user_jid`, `state`, `whatsapp_client`). Add an `__init__` method.
    *   Refactor specific workflow classes (`MergeWorkflow`, etc.) to use instance methods instead of static methods. State should be managed within the instance (`self.state`).
    *   Modify `WorkflowManager`:
        *   When starting a workflow, instantiate the appropriate workflow class (passing `whatsapp_client`, `task_id`, etc.).
        *   Store an identifier or the instance itself (depending on persistence) associated with the `sender_jid`.
        *   Delegate calls (`handle_file_save`, `handle_command`) directly to the loaded workflow instance.
        *   Inject the `WhatsAppClient` instance into the workflow instance upon creation.

11. **Implement Robust External Tool Error Handling:** ✅
    *   Enhance the wrappers in `utils/external_tools.py`:
        *   Add tool existence checks (`shutil.which`) raising `ToolNotFoundError`.
        *   Parse `stderr` for known error patterns specific to each tool (LibreOffice, Ghostscript, etc.).
        *   Raise more specific exceptions (e.g., `LibreOfficeError`, `GhostscriptError`) containing parsed details.
        *   Ensure consistent timeout usage. Log full command, stdout, stderr, and return code on failure.

12. **Implement Granular Exception Handling & User Feedback:** ✅
    *   Use `finally` blocks to ensure cleanup (`cleanup_task_universal`) runs even if errors occur during processing.
    *   Enhanced error handling in `_finalize_workflow` to improve user feedback and handle errors gracefully.
    *   Added error isolation for separate components of the workflow finalization process.

13. **Secure File Handling and Cleanup:** ✅
    *   Added robust error handling within `cleanup_task_universal` to handle each file operation independently.
    *   Implemented file existence/completion checks with `check_file_exists_and_complete` function.
    *   Added path sanitization with `sanitize_filename` and `ensure_safe_path` functions.
    *   Implemented atomic writes/renames using temporary files with `safe_write_file`.
    *   Enhanced `cleanup_task_universal` to continue cleanup even if some operations fail.

**Phase 3: Performance and Scalability**

14. **Implement Asynchronous Processing (Task Queue):** ✅
    *   Set up Celery with Redis for task queuing by adding Celery to requirements.txt.
    *   Created Celery configuration in settings.py including broker URLs, timeouts, and serialization options.
    *   Created Celery app module (app/celery_app.py) with worker availability checking.
    *   Defined Celery tasks for long-running operations in app/tasks.py:
        *   `compress_pdf_task` for PDF compression.
        *   `convert_document_task` for office document conversions.
        *   `merge_pdfs_task` for PDF merging.
        *   `split_pdf_task` for PDF splitting.
        *   `process_scan_task` for image to PDF processing.
    *   Implemented fallback to synchronous execution when Celery is disabled or unavailable.
    *   Added detailed logging and error handling for all asynchronous tasks.

15. **Optimize External Tool Usage:**
    *   Investigate and implement LibreOffice server mode (`unoconv` listener or `soffice --accept=...`) if feasible within the deployment environment (Docker makes this easier) to reduce startup overhead. Update tool wrappers accordingly.
    *   Review and potentially tune Ghostscript parameters (`-dPDFSETTINGS`, DPI) based on testing and requirements. Make them configurable via `settings.py`.

16. **Optimize File I/O:**
    *   Review `pypdf` usage – use streaming methods if available for large PDFs.
    *   Investigate if `evolution-api-pythonclient` supports streaming downloads/uploads to avoid loading large files entirely into memory. Adapt `whatsapp_client.py` if possible.

**Phase 4: User Experience, Advanced Features & Operations**

17. **Enhance User Feedback:**
    *   Implement a "cancel" command: Check for it in `WorkflowManager.handle_message`. If detected for an active workflow, update the state to 'cancelled', potentially attempt to terminate running tasks (if using Celery), and notify the user.
    *   For tasks running in the queue (Step 14), implement status updates: The task can update its state in the persistent store (e.g., 'processing page 5/10'). The main app could potentially query this, or the task could send intermediate messages (use carefully to avoid spam).

18. **Improve Workflow-Specific Logic:**
    *   Refactor `ExcelToPdfWorkflow`: Investigate direct `libreoffice --convert-to` filter options to replace the complex user profile method if possible.
    *   Refine `MarkdownToPdfWorkflow`: Ensure robust error parsing between fallback steps.
    *   Define and enforce a clear contract (args, exit codes, stderr) for `scanner.py` and ensure the tool wrapper handles it.

19. **Containerization (Docker):**
    *   Create/Refine `Dockerfile`: Install Python, system dependencies (LibreOffice, Ghostscript, Pandoc, etc.), copy application code, install Python requirements. Use multi-stage builds to keep the final image smaller.
    *   Create `docker-compose.yml`: Define services for the main app, Celery worker(s), Redis (for task queue/state). Define volumes for persistent data (`DOWNLOAD_BASE_DIR`).

20. **Configuration Management:**
    *   Move all remaining hardcoded values (timeouts, paths, quality settings, filenames like `merge_order.json`) to settings.py and load via environment variables (`.env`).

21. **Security Hardening:**
    *   Add dependency vulnerability scanning to the process: `pip install safety && safety check -r requirements.txt` or `pip-audit`. Integrate into CI (Step 22).
    *   Review file permissions for task directories.

22. **Setup CI Pipeline:**
    *   Use GitHub Actions, GitLab CI, or similar.
    *   Configure jobs to run on push/merge:
        *   Linting (`flake8`)
        *   Formatting check (`black --check`)
        *   Type checking (`mypy .`)
        *   Unit & Integration Tests (`pytest`)
        *   (Optional) Build Docker image.
        *   (Optional) Security scan (`safety`/`pip-audit`).

23. **Monitoring & Health Checks:**
    *   Add a simple health check endpoint (e.g., using Flask/FastAPI alongside the main app, or a separate script checking service responsiveness).
    *   (Advanced) Integrate Prometheus metrics (`prometheus-client`) for key indicators (tasks processed, errors, queue length).

This plan progresses from essential stability and testing towards more complex architectural changes and operational improvements, allowing for incremental development and validation.