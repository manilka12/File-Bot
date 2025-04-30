#!/usr/bin/env python3
import os
import subprocess
import datetime
import re

def run_command(command):
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        print(f"Error message: {e.stderr}")
        return None

def get_current_branch():
    """Get the name of the current git branch."""
    return run_command("git rev-parse --abbrev-ref HEAD")

def list_branches():
    """List all git branches with their descriptions."""
    # Get all branches
    branches_raw = run_command("git branch")
    if not branches_raw:
        return []
    
    branches = []
    for branch in branches_raw.split('\n'):
        branch = branch.strip()
        is_current = False
        if branch.startswith('*'):
            branch = branch[1:].strip()
            is_current = True
        
        # Get last commit message for this branch
        commit_msg = run_command(f"git log -1 --pretty=%B {branch}")
        branches.append({
            'name': branch,
            'description': commit_msg,
            'current': is_current
        })
    
    return branches

def check_status():
    """Check if there are uncommitted changes in the repository."""
    status = run_command("git status --porcelain")
    if status:
        print("\n[!] You have uncommitted changes:")
        print(status)
        return True
    return False

def commit_changes(branch_name=None, message=None):
    """Commit existing changes to the specified branch or current branch."""
    # Check if there are changes to commit
    status = run_command("git status --porcelain")
    if not status:
        print("No changes to commit.")
        return False
    
    # If branch name provided and it's not the current branch, switch to it
    current_branch = get_current_branch()
    switched = False
    if branch_name and branch_name != current_branch:
        # Stash changes before switching
        run_command("git stash")
        if not switch_to_branch(branch_name):
            print(f"Failed to switch to branch '{branch_name}'")
            run_command("git stash pop")  # Restore changes
            return False
        switched = True
        # Apply stashed changes
        run_command("git stash pop")
    
    # Ask for commit message if not provided
    if not message:
        print("\nChanges to commit:")
        print(status)
        message = input("\nEnter commit message: ")
        if not message:
            message = f"Changes committed on {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    
    # Add and commit changes
    run_command("git add -A")
    result = run_command(f'git commit -m "{message}"')
    
    # Switch back to original branch if needed
    if switched:
        switch_to_branch(current_branch)
    
    if result is not None:
        print(f"Changes committed successfully with message: '{message}'")
        return True
    else:
        print("Failed to commit changes.")
        return False

def delete_branch(branch_name):
    """Delete the specified branch."""
    current_branch = get_current_branch()
    if branch_name == current_branch:
        print(f"Cannot delete the current branch '{branch_name}'.")
        return False
    
    result = run_command(f"git branch -d {branch_name}")
    if result is not None:
        print(f"Deleted branch '{branch_name}'")
        return True
    
    # If normal delete fails, ask if user wants to force delete
    choice = input(f"Branch '{branch_name}' has unmerged changes. Force delete? (y/N): ").lower()
    if choice == 'y':
        result = run_command(f"git branch -D {branch_name}")
        if result is not None:
            print(f"Force deleted branch '{branch_name}'")
            return True
    return False

def create_snapshot():
    """Create a new snapshot (branch) of the current state."""
    # Generate timestamp in the desired format
    timestamp = datetime.datetime.now().strftime("%d/%m %H:%M")
    
    # Ask for additional identification text
    additional_info = input("Enter additional identification text for this snapshot: ")
    
    # Create branch name
    branch_name = f"snap_{timestamp.replace('/', '_').replace(':', '_')}"
    if additional_info:
        # Convert additional info to a valid git branch name (remove spaces and special chars)
        safe_info = re.sub(r'[^a-zA-Z0-9_-]', '_', additional_info)
        branch_name += f"_{safe_info}"
    
    # Create commit message
    message = f"Snapshot {timestamp}"
    if additional_info:
        message += f" - {additional_info}"
    
    # Check if we're in a git repository
    if not os.path.exists(".git"):
        print("Initializing Git repository...")
        run_command("git init")
    
    # Add all files to staging
    print("Adding all files to Git...")
    run_command("git add -A")
    
    # Create a commit
    print(f"Creating commit: {message}")
    run_command(f'git commit -m "{message}"')
    
    # Create and switch to the new branch
    print(f"Creating branch: {branch_name}")
    run_command(f"git branch {branch_name}")
    
    print(f"\nSnapshot saved successfully as branch '{branch_name}'")

def switch_to_branch(branch_name):
    """Switch to the specified branch."""
    result = run_command(f"git checkout {branch_name}")
    if result is not None:
        print(f"Switched to branch '{branch_name}'")
        return True
    return False

def main():
    """Main menu function."""
    # Check if we're in a git repository
    if not os.path.exists(".git"):
        print("Initializing Git repository...")
        run_command("git init")
        print("Git repository initialized.")
    
    # Check status when script starts
    has_changes = check_status()
    
    while True:
        current_branch = get_current_branch()
        branches = list_branches()
        
        print("\n" + "="*50)
        print(f"You are on branch: {current_branch}")
        print("="*50)
        
        print("\nOptions:")
        print("1. Create new snapshot branch")
        print("2. Go to existing branch")
        print("3. Commit changes to current branch")
        print("4. Commit changes to different branch")
        print("5. Delete a branch")
        print("6. Check status")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-6): ").strip()
        
        if choice == "1":
            create_snapshot()
        
        elif choice == "2":
            if not branches:
                print("No branches found.")
                continue
            
            print("\nAvailable branches:")
            for i, branch in enumerate(branches, 1):
                current_marker = " (current)" if branch['current'] else ""
                print(f"{i}. {branch['name']}{current_marker}")
                print(f"   Description: {branch['description']}")
            
            branch_choice = input("\nEnter branch number or 0 to cancel: ").strip()
            if branch_choice.isdigit():
                branch_idx = int(branch_choice) - 1
                if 0 <= branch_idx < len(branches):
                    switch_to_branch(branches[branch_idx]['name'])
                elif branch_idx == -1:
                    print("Operation cancelled.")
                else:
                    print("Invalid branch number.")
        
        elif choice == "3":
            commit_changes()
        
        elif choice == "4":
            if not branches:
                print("No branches found.")
                continue
            
            print("\nAvailable branches:")
            for i, branch in enumerate(branches, 1):
                current_marker = " (current)" if branch['current'] else ""
                print(f"{i}. {branch['name']}{current_marker}")
                print(f"   Description: {branch['description']}")
            
            branch_choice = input("\nEnter branch number or 0 to cancel: ").strip()
            if branch_choice.isdigit():
                branch_idx = int(branch_choice) - 1
                if 0 <= branch_idx < len(branches):
                    commit_changes(branches[branch_idx]['name'])
                elif branch_idx == -1:
                    print("Operation cancelled.")
                else:
                    print("Invalid branch number.")
        
        elif choice == "5":
            if not branches:
                print("No branches found.")
                continue
            
            print("\nAvailable branches:")
            for i, branch in enumerate(branches, 1):
                current_marker = " (current)" if branch['current'] else ""
                print(f"{i}. {branch['name']}{current_marker}")
                print(f"   Description: {branch['description']}")
            
            branch_choice = input("\nEnter branch number or 0 to cancel: ").strip()
            if branch_choice.isdigit():
                branch_idx = int(branch_choice) - 1
                if 0 <= branch_idx < len(branches):
                    delete_branch(branches[branch_idx]['name'])
                elif branch_idx == -1:
                    print("Operation cancelled.")
                else:
                    print("Invalid branch number.")
        
        elif choice == "6":
            if check_status():
                print("\nWould you like to commit these changes? (y/N): ", end="")
                if input().lower() == 'y':
                    commit_changes()
            else:
                print("Working directory is clean. No changes to commit.")
        
        elif choice == "0":
            # Check for uncommitted changes before exiting
            if check_status():
                print("\nYou have uncommitted changes. Would you like to commit them before exiting? (y/N): ", end="")
                if input().lower() == 'y':
                    commit_changes()
            print("Exiting. Goodbye!")
            break
        
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()