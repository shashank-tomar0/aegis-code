"""
aegis/classroom.py — GitHub Classroom API Integration

Fetches student repository URLs directly from a GitHub Classroom assignment
using the GitHub REST API. This allows bulk cloning without needing a manual
list of repository URLs.
"""

import requests
import json
import os
from aegis.ui import print_info, print_error, print_success

# GitHub API endpoints
GH_API_BASE = "https://api.github.com"

def fetch_classroom_repos(assignment_id: str, github_token: str) -> list:
    """
    Fetches the list of accepted student repositories for a given assignment ID.
    Requires a GitHub Personal Access Token with appropriate scopes.
    """
    if not github_token:
        print_error("GitHub token not provided. Please set it in aegis.json or GITHUB_TOKEN environment variable.")
        return []

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    url = f"{GH_API_BASE}/assignments/{assignment_id}/accepted_assignments"
    print_info(f"Fetching student repositories for assignment ID: {assignment_id}...")
    
    repos = []
    page = 1
    
    try:
        while True:
            resp = requests.get(f"{url}?page={page}&per_page=100", headers=headers)
            
            if resp.status_code == 404:
                print_error(f"Assignment ID {assignment_id} not found. Ensure you have the correct ID and your token has organization access.")
                break
                
            resp.raise_for_status()
            data = resp.json()
            
            if not data:
                break
                
            for item in data:
                repo_info = item.get("repository", {})
                clone_url = repo_info.get("clone_url")
                if clone_url:
                    repos.append(clone_url)
                    
            page += 1
            
    except requests.exceptions.RequestException as e:
        print_error(f"Failed to fetch repositories from GitHub API: {e}")
        
    if repos:
        print_success(f"Successfully fetched {len(repos)} repository URLs from GitHub Classroom.")
        
    return repos

def extract_assignment_id(url_or_id: str) -> str:
    """
    Attempts to extract an assignment ID from a URL, or returns it as-is if it looks like an ID.
    Note: GitHub Classroom URLs are often `classroom.github.com/a/ID`.
    """
    if "classroom.github.com" in url_or_id:
        # Example: https://classroom.github.com/a/abcdefg
        parts = url_or_id.rstrip('/').split('/')
        if parts[-2] == 'a' or parts[-2] == 'classrooms':
            return parts[-1]
    return url_or_id
