import os

class DeploymentConfigError(Exception):
    pass

class DeploymentConfigParser:
    """
    Parses a strict deployment.txt configuration file.
    No guessing allowed.
    """
    MANDATORY_FIELDS = {
        "project_name",
        "start_command"
    }

    def parse(self, source_dir: str) -> dict:
        target_file = os.path.join(source_dir, "deployment.txt")
        
        if not os.path.exists(target_file):
            raise DeploymentConfigError("deployment.txt is missing. Strict configuration is mandatory.")
            
        config = {}
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        lines = content.splitlines()
        
        current_section = None
        current_block = []
        in_code_block = False
        
        for line in lines:
            stripped = line.strip()
            
            # Markdown Headings
            if stripped.startswith("## Build Command"):
                current_section = "build_command"
                in_code_block = False
                continue
            elif stripped.startswith("## Start Command"):
                current_section = "start_command"
                in_code_block = False
                continue
                
            # Code block toggles
            if current_section and stripped.startswith("```"):
                if in_code_block:
                    # Closing the block
                    config[current_section] = "\n".join(current_block).strip()
                    current_section = None
                    current_block = []
                    in_code_block = False
                else:
                    in_code_block = True
                continue
                
            if in_code_block:
                current_block.append(line)
                continue
                
            if not stripped or stripped.startswith("#"):
                continue
                
            if "=" in stripped:
                key, val = stripped.split("=", 1)
                # Make parsing extremely lenient: remove '#' and replace spaces with '_'
                key = key.strip(" #").replace(" ", "_").lower()
                val = val.strip()
                
                if val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False
                elif val.isdigit():
                    val = int(val)
                    
                config[key] = val
                
        # Validate mandatory fields
        missing_fields = self.MANDATORY_FIELDS - set(config.keys())
        if missing_fields:
            raise DeploymentConfigError(f"deployment.txt is missing mandatory fields: {', '.join(missing_fields)}")
            
        return config
