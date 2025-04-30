#!/usr/bin/env python3
import os
import subprocess
import datetime
import re
import sys # Import sys for sys.exit

def run_command(command):
    """Run a shell command and return its output."""
    #print(f"Executing: {command}") # Added for debugging
    try:
        # Using list format is generally safer than shell=True
        if isinstance(command, str):
            command_list = command.split()
        else:
            command_list = command

        result = subprocess.run(command_list, capture_output=True, text=True, check=False) # Use check=False to handle errors manually

        if result.returncode != 0:
            # Handle common git errors gracefully
            if "nothing to commit, working tree clean" in result.stderr:
                 print("Info: Working tree clean, no changes to commit.")
                 return "" # Return empty string, not None, to indicate success but no action
            elif "did not match any file(s) known to git" in result.stderr and command_list[1] == 'add':
                 print("Info: No files to add.")
                 return "" # Return empty string
            elif "no changes added to commit" in result.stderr and command_list[1] == 'commit':
                 print("Info: No changes staged for commit.")
                 return "" # Return empty string
            elif "Aborting commit due to empty commit message" in result.stdout:
                 print("Error: Commit aborted due to empty message.")
                 return None
            # Handle branch exists error specifically for checkout -b
            elif "already exists" in result.stderr and command_list[1] == 'checkout' and command_list[2] == '-b':
                print(f"Error: Branch '{command_list[3]}' already exists.")
                return None
            # Handle branch exists error specifically for branch creation
            elif "already exists" in result.stderr and command_list[1] == 'branch' and len(command_list) > 2:
                 print(f"Error: Branch '{command_list[2]}' already exists.")
                 return None

            # Generic error
            print(f"Error executing command: {' '.join(command_list)}")
            print(f"Stderr: {result.stderr.strip()}")
            print(f"Stdout: {result.stdout.strip()}")
            return None
        else:
            # print(f"Success: {result.stdout.strip()}") # Optional: Print success output
            return result.stdout.strip()

    except FileNotFoundError:
        print(f"Error: Command not found. Is Git installed and in your PATH?")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_current_branch():
    """Get the name of the current git branch."""
    # Use rev-parse which is more robust for scripting
    branch = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    # Handle detached HEAD state
    if branch == "HEAD":
        # Get the commit hash instead
        commit_hash = run_command(["git", "rev-parse", "--short", "HEAD"])
        return f"DETACHED HEAD ({commit_hash})"
    return branch

def list_branches():
    """List all git branches with their descriptions (last commit message)."""
    branches_raw = run_command(["git", "branch", "--format=%(refname:short)"])
    if branches_raw is None: # Check if command failed
        return []
    if not branches_raw:
        return []

    branches_list = branches_raw.strip().split('\n')
    current_branch_name = get_current_branch() # Get current branch once

    branches_info = []
    for branch_name in branches_list:
        branch_name = branch_name.strip()
        if not branch_name: continue # Skip empty lines if any

        # Get last commit message for this branch
        # Use --no-pager to prevent potential interactive prompts
        commit_msg = run_command(["git", "--no-pager", "log", "-1", "--pretty=format:%s", branch_name]) # Just get subject line for brevity
        if commit_msg is None:
            commit_msg = "Error fetching commit message" # Handle potential error

        branches_info.append({
            'name': branch_name,
            'description': commit_msg,
            'current': branch_name == current_branch_name
        })

    return branches_info

def check_status():
    """Check if there are uncommitted changes in the repository."""
    status = run_command(["git", "status", "--porcelain"])
    if status is None: # Command failed
        return False # Assume no changes or cannot determine
    if status:
        print("\n[!] You have uncommitted changes/untracked files:")
        print(status)
        return True
    return False

def commit_changes(branch_name=None, message=None):
    """Commit existing changes to the specified branch or current branch."""
    current_branch = get_current_branch()
    target_branch = branch_name or current_branch

    # Prevent committing to another branch if the working directory is dirty
    if target_branch != current_branch:
        print(f"Checking status before potential switch to '{target_branch}'...")
        status_output = run_command(["git", "status", "--porcelain"])
        if status_output:
            print(f"\n[!] You have uncommitted changes on '{current_branch}'.")
            print("Please commit or stash them first before committing to a different branch.")
            print("Use option 3 (Commit to current) or 6 (Check status) first.")
            return False
        # If clean, we can switch (though this function *only* commits, doesn't switch permanently)
        # The original script's stash logic was complex and removed.
        # For simplicity, this function now ONLY commits to the *current* branch if target_branch is different and WDIR is clean.
        # To commit to another branch, the user should check out that branch first (Option 2).
        # Let's refine this: Option 4 should probably be removed or re-thought.
        # Sticking to the original intent *without* the risky stash:
        # We won't switch branches here. If branch_name is specified, we ensure it exists,
        # but the commit happens on the *current* branch. This seems wrong.
        # --> Let's make Option 4 *require* switching first via Option 2.
        # --> Or, let's *remove* Option 4 and simplify. Users can use Option 2 then Option 3.

        # ---> Decision: Keep Option 4 BUT make it simply call commit_changes with message ONLY.
        #      The commit will ALWAYS happen on the CURRENT branch. Option 4 becomes redundant.
        # ---> Alternative Decision: Modify Option 4's description: "Commit changes (will commit to CURRENT branch)".
        # ---> Best Decision: Remove the complex 'commit to different branch' logic entirely for safety and simplicity.
        #      Users should explicitly switch branches (Option 2) then commit (Option 3).
        # Let's modify this function to ONLY commit to the current branch.
        print(f"Committing changes to the current branch: '{current_branch}'")


    # Check if there are changes to commit (staged or unstaged)
    status_output_for_commit = run_command(["git", "status", "--porcelain"])
    if not status_output_for_commit:
        print(f"No changes detected on branch '{current_branch}'. Nothing to commit.")
        return False

    # Ask for commit message if not provided
    if not message:
        print("\nChanges to be committed:")
        print(status_output_for_commit) # Show the status again
        message = input(f"\nEnter commit message for branch '{current_branch}': ")
        if not message:
            # Provide a default message or abort? Let's abort.
            print("Commit message cannot be empty. Aborting commit.")
            # message = f"Auto-commit on {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
            return False

    # Add all changes (tracked and untracked)
    print("Staging all changes...")
    add_result = run_command(["git", "add", "-A"])
    if add_result is None:
        print("Failed to stage changes.")
        return False

    # Check again if anything was actually staged
    staged_status = run_command(["git", "diff", "--cached", "--quiet"])
    # run_command returns stdout. `git diff --cached --quiet` exits with 1 if there are staged changes, 0 otherwise.
    # We need to check the return code directly here, or refine run_command.
    # Let's simplify: Assume `git add -A` worked and attempt commit. `git commit` will tell us if nothing was staged.

    # Commit the changes
    print(f"Committing with message: '{message}'")
    # Ensure quotes are handled if the message contains them (use list format for command)
    commit_command = ["git", "commit", "-m", message]
    commit_result = run_command(commit_command)

    if commit_result is not None:
        # Check if the commit actually happened (it might return "" if nothing was committed)
        if "nothing to commit" in commit_result or "no changes added to commit" in commit_result or not commit_result:
             # Check the actual status again to be sure
             staged_check_after_commit = run_command(["git", "status", "--porcelain"])
             if not staged_check_after_commit:
                 print(f"Looks like there were no changes to commit on '{current_branch}'.")
                 # This case shouldn't be reached if the initial status check worked, but adding safety.
                 return False # Indicate no actual commit happened
             else:
                 # This indicates an issue with detecting commit success/failure
                 print(f"Commit attempted, but status still shows changes. Please check manually.")
                 return False

        print(f"Changes committed successfully to branch '{current_branch}'")
        return True
    else:
        # Error message was already printed by run_command
        print("Failed to commit changes.")
        return False


def delete_branch(branch_name):
    """Delete the specified branch."""
    current_branch = get_current_branch()
    if branch_name == current_branch:
        print(f"Cannot delete the current branch '{branch_name}'. Switch to another branch first.")
        return False

    print(f"Attempting to delete branch '{branch_name}'...")
    # Use lowercase -d for safe delete first
    delete_result = run_command(["git", "branch", "-d", branch_name])

    if delete_result is not None:
        # Success is often indicated by an empty output or specific message
        # Let's check the stderr for common success/failure messages
        if "Deleted branch" in delete_result or delete_result == "":
             print(f"Successfully deleted branch '{branch_name}'.")
             return True
        else:
            # Deletion might have failed safely (e.g., unmerged changes)
            # run_command should have printed stderr, but we can check again
            check_again = run_command(['git', 'branch', '--list', branch_name])
            if branch_name in check_again: # Branch still exists
                 print(f"Could not delete branch '{branch_name}'. It might have unmerged changes.")
                 choice = input(f"Force delete '{branch_name}'? This is irreversible. (y/N): ").lower()
                 if choice == 'y':
                     print(f"Attempting to force delete branch '{branch_name}'...")
                     force_delete_result = run_command(["git", "branch", "-D", branch_name])
                     if force_delete_result is not None:
                          print(f"Force deleted branch '{branch_name}'.")
                          return True
                     else:
                          print(f"Failed to force delete branch '{branch_name}'.")
                          return False
                 else:
                     print("Deletion cancelled.")
                     return False
            else:
                 # This case is unlikely if -d failed, but maybe it was deleted somehow?
                 print(f"Branch '{branch_name}' seems to be deleted, but the initial command reported an issue.")
                 return True # Assume deleted

    # If delete_result is None, run_command already printed the error
    return False

def create_snapshot():
    """Creates a new branch capturing the current state (including uncommitted changes)."""
    print("\n--- Create Snapshot ---")
    current_branch = get_current_branch()
    if "DETACHED HEAD" in current_branch:
        print("Error: Cannot create a snapshot from a DETACHED HEAD state.")
        print("Please checkout a branch first using option 2.")
        return

    # Generate timestamp
    timestamp = datetime.datetime.now().strftime("%d%m%y_%H%M%S") # Made git-friendlier

    # Ask for additional identification text
    additional_info = input("Enter brief description for this snapshot (e.g., 'before_refactor'): ").strip()

    # Create branch name (sanitize info)
    safe_info = re.sub(r'[^a-zA-Z0-9_-]', '_', additional_info)
    safe_info = re.sub(r'_+', '_', safe_info).strip('_') # Replace multiple underscores and trim ends

    branch_name = f"snap_{timestamp}"
    if safe_info:
        branch_name += f"_{safe_info}"

    # Create commit message
    commit_message = f"Snapshot {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}"
    if additional_info:
        commit_message += f" - {additional_info}"

    print(f"\nSnapshot details:")
    print(f"  Branch Name: {branch_name}")
    print(f"  Commit Msg:  {commit_message}")
    confirm = input("Proceed? (Y/n): ").lower()
    if confirm == 'n':
        print("Snapshot creation cancelled.")
        return

    # --- Start Snapshot Git Workflow ---
    print(f"\nCreating snapshot branch '{branch_name}' from '{current_branch}'...")

    # 1. Create the new branch from the current HEAD *without* checking it out yet
    create_branch_result = run_command(["git", "branch", branch_name])
    if create_branch_result is None:
        # Error handled by run_command (e.g., branch already exists)
        return

    print(f"Branch '{branch_name}' created.")

    # 2. Check out the new snapshot branch
    print(f"Checking out '{branch_name}'...")
    checkout_result = run_command(["git", "checkout", branch_name])
    if checkout_result is None:
        print(f"Error: Failed to checkout snapshot branch '{branch_name}'.")
        # Attempt to cleanup the created branch? Maybe too risky.
        print("Please resolve manually.")
        # Attempt to switch back just in case something partial happened
        run_command(["git", "checkout", current_branch])
        return

    # 3. Stage all changes (tracked and untracked) on the new branch
    print("Staging all current changes for the snapshot commit...")
    add_result = run_command(["git", "add", "-A"])
    if add_result is None:
        print("Error: Failed to stage changes for snapshot.")
        print(f"Switching back to '{current_branch}'.")
        run_command(["git", "checkout", current_branch])
        return

    # 4. Commit the staged changes on the snapshot branch
    #    Use --allow-empty to ensure a commit is made even if the working dir was clean,
    #    clearly marking the snapshot point in this branch's history.
    print(f"Creating snapshot commit on '{branch_name}'...")
    commit_command = ["git", "commit", "--allow-empty", "-m", commit_message]
    commit_result = run_command(commit_command)

    if commit_result is None:
        print("Error: Failed to create snapshot commit.")
        print(f"Switching back to '{current_branch}'.")
        run_command(["git", "checkout", current_branch])
        return
    elif "nothing to commit" in commit_result or "no changes added" in commit_result:
         # This might happen if --allow-empty wasn't effective or add failed silently
         print("Warning: Snapshot commit seems empty. The branch points to the pre-snapshot state.")
         # Still proceed to switch back

    # 5. Switch back to the original branch
    print(f"Switching back to original branch '{current_branch}'...")
    switch_back_result = run_command(["git", "checkout", current_branch])
    if switch_back_result is None:
        print(f"Error: Failed to switch back to '{current_branch}'.")
        print(f"You are currently on the snapshot branch '{branch_name}'.")
        # Don't exit, let the user see the state.
    else:
        print(f"Successfully created snapshot branch '{branch_name}'.")
        print(f"You are back on '{current_branch}'.")

    print("\nSnapshot creation process finished.")
    # --- End Snapshot Git Workflow ---


def switch_to_branch(branch_name):
    """Switch to the specified branch."""
    current_branch = get_current_branch()
    if branch_name == current_branch:
        print(f"You are already on branch '{branch_name}'.")
        return True

    # Check for uncommitted changes before switching
    print("Checking for uncommitted changes before switching...")
    if check_status(): # This function already prints the status
        print(f"\n[!] Cannot switch branch: You have uncommitted changes on '{current_branch}'.")
        print("Please commit (Option 3) or stash them first.")
        # Add instructions for stashing if desired:
        # print("You can stash them using: git stash push -m 'WIP on {current_branch}'")
        # print("And restore later using: git stash pop")
        return False

    print(f"Switching to branch '{branch_name}'...")
    result = run_command(["git", "checkout", branch_name])
    if result is not None:
        # run_command will print stderr on failure. Success often has specific stdout.
        if "Switched to branch" in result or "Already on" in result or result.startswith("Your branch is up to date"):
            print(f"Successfully switched to branch '{branch_name}'.")
            return True
        else:
            # Checkout might succeed but with warnings, run_command might return stdout
            print(f"Switched to branch '{branch_name}'. (Output: {result})")
            return True # Assume success if result is not None
    else:
        # Error message already printed by run_command
        print(f"Failed to switch to branch '{branch_name}'.")
        return False

def initialize_git_repo():
    """Initialize a Git repository if one doesn't exist."""
    if not os.path.exists(".git"):
        print("No Git repository detected.")
        choice = input("Initialize a new Git repository here? (Y/n): ").lower()
        if choice == 'n':
            print("Exiting. Cannot proceed without a Git repository.")
            sys.exit(1) # Exit the script
        else:
            print("Initializing Git repository...")
            init_result = run_command(["git", "init"])
            if init_result is None:
                print("Error: Failed to initialize Git repository.")
                sys.exit(1) # Exit the script
            print("Git repository initialized.")
            # Optional: Make an initial commit?
            # print("Creating initial commit...")
            # run_command(["git", "add", "."]) # Add potentially existing files
            # run_command(["git", "commit", "--allow-empty", "-m", "Initial commit"])
    # Check if we can get a branch name now
    if get_current_branch() is None:
         print("Error: Could not determine current branch even after initialization.")
         print("There might be an issue with your Git setup.")
         sys.exit(1)


def main():
    """Main menu function."""
    # Check/Initialize Git repo at the start
    initialize_git_repo()

    # Check status when script starts
    print("\n--- Initial Status Check ---")
    check_status()

    while True:
        current_branch_name = get_current_branch()
        if current_branch_name is None:
             print("\nError: Lost connection to Git repository or cannot determine branch. Exiting.")
             break

        print("\n" + "="*50)
        print(f"Current Branch: {current_branch_name}")
        print("="*50)

        # Get branches fresh each time
        branches = list_branches()

        print("\nOptions:")
        print("1. Create Snapshot (New branch capturing current state)")
        print("2. Switch to Existing Branch")
        print("3. Commit Changes (Stages all changes on current branch)")
        print("4. Delete a Branch")
        print("5. Check Status / List Uncommitted Changes")
        print("0. Exit")

        choice = input("\nEnter your choice (0-5): ").strip()

        if choice == "1":
            create_snapshot()

        elif choice == "2":
            if not branches:
                print("No branches found.")
                continue

            print("\nAvailable branches:")
            # Sort branches, putting current first? Or just list alphabetically? Alphabetical is fine.
            sorted_branches = sorted(branches, key=lambda x: x['name'])
            branch_map = {} # To map choice number back to branch name
            for i, branch in enumerate(sorted_branches, 1):
                current_marker = " (current)" if branch['current'] else ""
                # Limit description length
                desc = branch['description']
                desc_short = (desc[:75] + '...') if len(desc) > 75 else desc
                print(f"{i}. {branch['name']}{current_marker}")
                print(f"   Last Commit: {desc_short}")
                branch_map[str(i)] = branch['name']

            branch_choice = input("\nEnter branch number to switch to (or 0 to cancel): ").strip()
            if branch_choice == '0':
                print("Operation cancelled.")
            elif branch_choice in branch_map:
                switch_to_branch(branch_map[branch_choice])
            else:
                print("Invalid branch number.")

        elif choice == "3":
            # Commit changes on the current branch
            commit_changes() # No branch name needed, it works on current

        # Option 4 was commit to different branch - removing as it's complex/unsafe without careful handling
        # Renumbering subsequent options
        elif choice == "4": # Was 5
             if not branches:
                 print("No branches found to delete.")
                 continue

             print("\nAvailable branches to delete:")
             delete_options = {}
             count = 1
             for i, branch in enumerate(branches):
                 # Don't list the current branch as an option to delete here
                 if not branch['current']:
                     print(f"{count}. {branch['name']}")
                     print(f"   Last Commit: {branch['description']}")
                     delete_options[str(count)] = branch['name']
                     count += 1

             if not delete_options:
                  print(f"Only the current branch ('{current_branch_name}') exists. Cannot delete it.")
                  continue

             branch_choice = input("\nEnter branch number to delete (or 0 to cancel): ").strip()
             if branch_choice == '0':
                 print("Operation cancelled.")
             elif branch_choice in delete_options:
                 delete_branch(delete_options[branch_choice])
             else:
                 print("Invalid branch number.")


        elif choice == "5": # Was 6
            print("\n--- Checking Git Status ---")
            if check_status():
                print("\nUse Option 3 to commit these changes.")
            else:
                print("Working directory is clean. No changes to commit.")

        elif choice == "0":
            # Check for uncommitted changes before exiting
            print("\nChecking for uncommitted changes before exiting...")
            if check_status():
                print("\n[!] You have uncommitted changes.")
                exit_confirm = input("Exit anyway? (y/N): ").lower()
                if exit_confirm != 'y':
                    print("Exit cancelled. Use Option 3 to commit changes.")
                    continue # Go back to menu
            print("\nExiting Git Helper. Goodbye!")
            break

        else:
            print("Invalid choice. Please try again.")

        # Pause briefly before showing the menu again
        # input("\nPress Enter to continue...")


if __name__ == "__main__":
    main()