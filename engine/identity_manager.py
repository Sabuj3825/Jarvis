"""
engine/identity_manager.py
==========================
Aggregates registry data for SYSTEM_IDENTITY requests.
"""

import json
import os

class IdentityManager:
    @staticmethod
    def get_system_identity() -> str:
        """Aggregates identity, capabilities, and system registry data into a structured format."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_dir = os.path.join(base_dir, "config")
        
        identity_file = os.path.join(config_dir, "identity.json")
        capabilities_file = os.path.join(config_dir, "capabilities.json")
        registry_file = os.path.join(config_dir, "system_registry.json")
        
        identity_data = {}
        if os.path.exists(identity_file):
            with open(identity_file, "r", encoding="utf-8") as f:
                identity_data = json.load(f)
                
        cap_data = {}
        if os.path.exists(capabilities_file):
            with open(capabilities_file, "r", encoding="utf-8") as f:
                cap_data = json.load(f)
                
        reg_data = {}
        if os.path.exists(registry_file):
            with open(registry_file, "r", encoding="utf-8") as f:
                reg_data = json.load(f)

        # Build structured response
        response = f"Name: {identity_data.get('name', 'JARVIS')} ({identity_data.get('full_name', '')})\n"
        response += f"Version: {identity_data.get('version', 'Unknown')} | Architecture: {identity_data.get('architecture', 'Unknown')}\n"
        response += f"Creator: {identity_data.get('creator', 'Unknown')} | Developer: {identity_data.get('developer', 'Unknown')}\n\n"
        
        response += f"Description: {identity_data.get('description', '')}\n"
        response += f"Primary Directive: {identity_data.get('primary_directive', '')}\n\n"
        
        response += "Capabilities:\n"
        if cap_data.get("ai_capabilities"):
            response += f"- AI Capabilities: {', '.join(cap_data['ai_capabilities'])}\n"
        if cap_data.get("local_commands"):
            response += f"- Local Commands: {', '.join(cap_data['local_commands'])}\n"
        if cap_data.get("knowledge_sources"):
            response += f"- Knowledge Sources: {', '.join(cap_data['knowledge_sources'])}\n"
            
        response += "\nSystem Modules:\n"
        if reg_data.get("modules"):
            for mod, path in reg_data["modules"].items():
                response += f"- {mod} ({path})\n"
                
        return response.strip()
