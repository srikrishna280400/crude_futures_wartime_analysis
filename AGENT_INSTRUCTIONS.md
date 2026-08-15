# 🚀 Agent Operational Playbook & Token Optimization Guide

    > [!IMPORTANT]
    > **READ THIS ENTIRE FILE BEFORE STARTING THE TASK OR EXECUTING THE WORKSPACE REPO SCAN.**
    > This project has a massive footprint (3.5M+ tokens). To avoid hitting rate limits (RPM/TPM) and to operate with maximum efficiency, you must strictly follow these instructions.

    ---

    ## 📋 General Rules of Engagement

    1. **Prioritize Targeted Reading**: Do not attempt to read or ingest massive source files in their entirety unless absolutely critical. Use targeted, line-specific file reads wherever possible.
    2. **Batch & Segment**: Solve complex or multi-layered files sequentially in localized segments (Map-Reduce style). Do not attempt to modify or synthesize 100+ lines of distinct edits in a single turn.
    3. **Handle Throttling Elegantly**: If you encounter any `429: Resource Exhausted` or `Rate limit exceeded` errors, immediately pause your current script execution, apply exponential backoff (wait 2s, then 4s, then 8s), and retry. Make sure you never run into that problem in the first place, know your limits beforehand, and adjust your strategy accordingly. 
    *YOU HAVE TO ABSOLUTELY IMPLEMENT THIS STRATEGY*
    4. Read the python code provided in the repo to understand the labelling/intent/purpose/background of the data. 
    5. Some of the data entries within each file and even across all files have been repeated, i.e have same column entry for every row (eg- source_timezone = 'UTC', currency_native = 'USD') so don't burn through tokens unnecessarily, just parse/process/understand it once throughout, so you don't have to lookup the column entries every time for every file and for every row within each file...since they are meant to be consistent all across.
    6. After reading this file and README.md, if you need any more additional MCP servers configured/connected that have not been configured already (from the existing 9) for executing this task, explicitly say so beforehand, to avoid unnecessary token burn, later on.
    7. Use the venv already set up at this place "/home/srikrishna/.venv-wsl-new/bin/activate" inside wsl-ubuntu if needed for installing scripts/libraries/frameworks, etc

    ---

    ## 🛠️ Step-by-Step Execution Plan

    ### Step 1: High-Level Indexing (Do NOT Read Code Yet)
    * Utilize file tree maps or search-based tools (`grep_search`) to locate filenames, classes, and specific function signatures.
    * Build an internal mental model of where things are before choosing which files to open.

    ### Step 2: Read Precisely
    * When opening a file, use exact line coordinates (e.g., `StartLine` and `EndLine` in `view_file`) instead of reading the entire file.
    * You must read every file completely in this repo, but do it **once** and store the structured summary or outline internally to prevent repeat reads.

    ### Step 3: Segmented Modifications
    * When writing or editing code, prefer small, incremental, targeted edits (`replace_file_content` or `multi_replace_file_content` targeting highly specific lines) rather than rewriting large sections of files.
    * Ensure all terminal compilations and test suite runs are targeted at the module you edited, rather than executing the entire test system.

    ### Step 4: Frequent Context Pruning
    * Periodically summarize your progress and discard intermediate scratch data to keep your active prompt history brief and crisp.
    * This ensures we maintain a highly optimized TPM (Tokens Per Minute) usage profile throughout the execution of this task.
