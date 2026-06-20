def classify_error(error_type: str, message: str):
    """
    Standardize error categories and provide Root Cause, Recommendation, Possible Causes, and Suggested Checks.
    """
    diagnostic = {
        "root_cause": None,
        "recommendation": None,
        "possible_causes": [],
        "suggested_checks": [],
        "technical_details": message
    }

    if "Clone" in error_type or error_type == "CLONE_FAILED":
        diagnostic["root_cause"] = "The system could not download your repository."
        diagnostic["recommendation"] = "Verify the clone URL is correct and the branch exists."
    
    elif "Config" in error_type or error_type == "CONFIGURATION_ERROR":
        if "deployment.txt is missing mandatory fields" in message.lower():
            diagnostic["root_cause"] = "deployment.txt is incomplete"
            diagnostic["recommendation"] = "Your `deployment.txt` is missing required fields. Ensure it has: project_name, start_command, port, health_check, runtime, and ssl."
        elif "deployment.txt is missing" in message.lower():
            diagnostic["root_cause"] = "deployment.txt is missing"
            diagnostic["recommendation"] = "Create a file named `deployment.txt` exactly in the root directory of your GitHub repository."
        else:
            diagnostic["root_cause"] = "Unknown"
            diagnostic["possible_causes"] = [
                "deployment.txt missing",
                "Invalid package.json",
                "Unsupported project structure",
                "Multiple entry points detected"
            ]
            diagnostic["suggested_checks"] = [
                "Ensure a valid deployment manifest exists.",
                "Check for typos in configuration files."
            ]

    elif "Container Start" in error_type or error_type == "STARTUP_FAILED":
        diagnostic["root_cause"] = "Unknown"
        diagnostic["possible_causes"] = [
            "start_command is incorrect",
            "Missing environment variables",
            "Code threw an exception immediately upon starting",
            "Port is blocked or unavailable"
        ]
        diagnostic["suggested_checks"] = [
            "Check if your start_command is correct.",
            "Verify all required environment variables are set.",
            "Review the application logs for early exceptions."
        ]

    elif "Health Check" in error_type or error_type == "HEALTH_CHECK_FAILED":
        diagnostic["root_cause"] = "Unknown"
        diagnostic["possible_causes"] = [
            "Port mismatch (app listening on different port)",
            "Application startup delay (app took too long to start)",
            "Missing health endpoint",
            "Reverse proxy configuration issue"
        ]
        diagnostic["suggested_checks"] = [
            "Verify listening port is 0.0.0.0 and matches deployment config.",
            "Test localhost inside container.",
            "Review application logs."
        ]

    elif "SSL" in error_type or error_type == "SSL_FAILED":
        diagnostic["root_cause"] = "Unknown"
        diagnostic["possible_causes"] = [
            "Domain DNS routing is incorrect",
            "Rate limits exceeded for SSL provider",
            "Internal network issue reaching SSL validation servers"
        ]
        diagnostic["suggested_checks"] = [
            "Check domain DNS routing.",
            "Verify you haven't hit Let's Encrypt rate limits."
        ]

    elif error_type == "ROLLBACK_FAILED":
        diagnostic["root_cause"] = "Attempt to restore the previous release failed."
        diagnostic["recommendation"] = "Manual recovery is required on the server."
        
    return diagnostic
