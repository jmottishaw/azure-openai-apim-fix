#!/usr/bin/env python3
"""
Azure OpenAI Spec Fixer for APIM Compatibility.

This script downloads the latest Azure OpenAI inference specification,
which is in OpenAPI 3.1.0 format and spread across multiple files. It then
performs several transformations to make it compatible with Azure API
Management (APIM) which expects a single, bundled OpenAPI 3.0.1 file.

Background:
    Azure OpenAI's 2025-04-01-preview specification uses OpenAPI 3.1.0 with
    external file references and new JSON Schema features that break APIM imports.
    See: https://github.com/Azure/azure-rest-api-specs/issues/35062

Transformations performed:
  1.  **Bundling**: Resolves all external file references (`$ref`) by
      downloading their content and embedding it, creating a single,
      self-contained specification file. Internal references are preserved.
  2.  **Compatibility Fixes**:
      - Removes OpenAPI 3.1.0-specific keywords (e.g., '$recursiveRef', 'propertyNames').
      - Fixes invalid 'description' fields that contain objects instead of strings.
      - Corrects 'discriminator' objects that are missing required properties.
  3.  **Version**: Keeps OpenAPI 3.1.0 by default (configurable for older APIM instances).

Requirements:
  - requests
  - jsonref

Usage:
  python3 fix_openai_spec.py

Output:
  Creates 'inference_fixed.json' ready for Azure APIM import.
"""

import json
import jsonref
import requests
from pathlib import Path
import copy
from typing import Dict, Any, List, Union
import argparse

# Configuration options
DOWNGRADE_TO_3_0_1 = True  # Set to True if your APIM instance requires OpenAPI 3.0.1

# Create a session object for better connection reuse
session = requests.Session()

def download_spec(url: str, output_file: str) -> None:
    """Download the OpenAPI spec from GitHub.
    
    Args:
        url: The GitHub raw URL to the OpenAPI specification
        output_file: Local file path where the spec will be saved
    """
    print(f"Downloading spec from {url}...")
    response = session.get(url)  # Use session for better connection reuse
    response.raise_for_status()
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response.text)
    print(f"Downloaded to {output_file}")

def fix_description_objects(obj: Union[Dict[str, Any], List[Any], Any]) -> None:
    """Recursively find 'description' fields that are objects and convert them to strings.
    
    APIM expects description fields to be simple strings, but some OpenAPI 3.1.0 specs
    incorrectly contain JSON objects in description fields, causing parsing errors.
    
    Args:
        obj: The OpenAPI specification object to process
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "description" and isinstance(value, dict):
                print(f"  Fixing complex description object...")
                # Convert the object to a JSON string representation
                obj[key] = json.dumps(value, indent=2)
            else:
                fix_description_objects(value)
    elif isinstance(obj, list):
        for item in obj:
            fix_description_objects(item)

def fix_discriminators(obj: Union[Dict[str, Any], List[Any], Any]) -> None:
    """
    Recursively find schemas with a 'discriminator' and ensure the discriminator property
    is in the 'required' list of all sub-schemas (oneOf, anyOf, allOf).
    
    OpenAPI discriminators require that the discriminating property (like 'type') be
    marked as required in every possible sub-schema. The Azure spec is missing this,
    causing validation errors in APIM.
    
    Args:
        obj: The OpenAPI specification object to process
    """
    if isinstance(obj, dict):
        # Check if this object itself is a schema with a discriminator
        if 'discriminator' in obj and 'propertyName' in obj['discriminator']:
            prop_name = obj['discriminator']['propertyName']
            print(f"  Fixing discriminator for property: '{prop_name}'")
            
            # Process all polymorphic schema combinations
            for key in ['oneOf', 'anyOf', 'allOf']:
                if key in obj:
                    for sub_schema in obj[key]:
                        # Ensure the sub-schema has a 'required' list
                        if 'required' not in sub_schema:
                            sub_schema['required'] = []
                        # Add the discriminator property if it's not already required
                        if prop_name not in sub_schema['required']:
                            sub_schema['required'].append(prop_name)
                            print(f"    Added '{prop_name}' to required list for a sub-schema.")

        # Continue traversing the rest of the spec recursively
        for key, value in obj.items():
            fix_discriminators(value)
            
    elif isinstance(obj, list):
        for item in obj:
            fix_discriminators(item)


def remove_unsupported_props(obj: Union[Dict[str, Any], List[Any], Any], path: str = "") -> None:
    """Remove OpenAPI 3.1.0 specific properties that are not supported in 3.0.1.
    
    OpenAPI 3.1.0 introduced new JSON Schema keywords that APIM doesn't recognize,
    causing import failures. These need to be stripped for 3.0.1 compatibility.
    
    Args:
        obj: The OpenAPI specification object to process
        path: Current path in the object tree (for logging)
    """
    if isinstance(obj, dict):
        removed = []
        # These are OpenAPI 3.1.0/JSON Schema keywords not supported in 3.0.1
        unsupported_props = ["$recursiveAnchor", "$recursiveRef", "propertyNames"]
        
        for prop in unsupported_props:
            if prop in obj:
                removed.append(prop)
                del obj[prop]
                
        if removed:
            print(f"  Removed {removed} from {path}")
            
        # Recursively process all nested objects
        for key, value in obj.items():
            remove_unsupported_props(value, f"{path}.{key}" if path else key)
            
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            remove_unsupported_props(item, f"{path}[{i}]")

def fix_openapi_spec(input_file: str, output_file: str, base_uri: str) -> None:
    """Apply a comprehensive series of transformations to make the Azure OpenAI spec APIM-compatible.
    
    This function orchestrates the complete transformation pipeline from OpenAPI 3.1.0
    to a clean, bundled 3.0.1 specification ready for Azure API Management import.
    
    Args:
        input_file: Path to the downloaded OpenAPI 3.1.0 specification
        output_file: Path where the fixed 3.0.1 specification will be saved
        base_uri: Base URI for resolving external file references
    """
    print(f"Loading spec from {input_file}...")
    
    # Load the spec with jsonref to enable reference resolution
    with open(input_file, 'r', encoding='utf-8') as f:
        spec_with_refs = jsonref.loads(f.read(), base_uri=base_uri)

    # Step 1: Bundle external references while preserving internal ones.
    # The official Azure spec is split across multiple files (./examples/*, etc.).
    # APIM needs a single, self-contained file, so we resolve external references
    # but preserve internal (#/) references as they're valid in OpenAPI 3.0.1.
    print("Bundling external references while preserving internal $refs...")
    
    # First, get the original spec to identify which refs were internal
    with open(input_file, 'r', encoding='utf-8') as f:
        original_spec = json.load(f)
    
    # Use deep copy to force resolution of all jsonref lazy objects
    # This handles the complex object serialization issues we encountered
    resolved_spec_data = copy.deepcopy(spec_with_refs)
    
    # Now restore internal $ref references where they existed in the original
    # This preserves the proper OpenAPI 3.0.1 structure while keeping bundled external content
    def restore_internal_refs(resolved_obj: Any, original_obj: Any) -> Any:
        """Recursively restore internal $ref references that should be preserved."""
        if isinstance(original_obj, dict) and isinstance(resolved_obj, dict):
            if "$ref" in original_obj and original_obj["$ref"].startswith("#/"):
                # This was an internal reference in the original - restore it
                return {"$ref": original_obj["$ref"]}
            else:
                # Process other dictionary items, merging resolved external content
                result = {}
                for key in resolved_obj:
                    if key in original_obj:
                        result[key] = restore_internal_refs(resolved_obj[key], original_obj[key])
                    else:
                        # This key came from external reference resolution - keep it
                        result[key] = resolved_obj[key]
                return result
        elif isinstance(original_obj, list) and isinstance(resolved_obj, list):
            result = []
            for i in range(len(resolved_obj)):
                if i < len(original_obj):
                    result.append(restore_internal_refs(resolved_obj[i], original_obj[i]))
                else:
                    result.append(resolved_obj[i])
            return result
        else:
            return resolved_obj
    
    print("Restoring internal $ref references...")
    clean_spec = restore_internal_refs(resolved_spec_data, original_spec)

    # Step 2: Fix discriminator mapping issues.
    # The source spec has polymorphism definitions ('discriminator') that are not
    # strictly compliant with OpenAPI requirements. APIM validates these strictly.
    print("Fixing discriminator properties...")
    fix_discriminators(clean_spec)

    # Step 3: Clean up complex description fields.
    # Some 'description' fields incorrectly contain JSON objects instead of
    # simple strings. APIM expects descriptions to be plain strings.
    print("Fixing complex description objects...")
    fix_description_objects(clean_spec)
    
    # Step 4: Optionally downgrade version for older APIM instances.
    # Modern APIM (stv2) accepts 3.1.0, but older instances may require 3.0.1
    if DOWNGRADE_TO_3_0_1:
        print("Downgrading OpenAPI version to 3.0.1...")
        clean_spec["openapi"] = "3.0.1"
    else:
        print("Preserving OpenAPI version 3.1.0 (recommended for modern APIM instances)")
    
    print("Removing OpenAPI 3.1.0 incompatible properties...")
    remove_unsupported_props(clean_spec)
    
    # Final Step: Save the fully APIM-compliant specification.
    print(f"Saving fixed spec to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(clean_spec, f, indent=2)
    
    print(f"Fixed spec saved to {output_file}")
    
    # Provide helpful statistics about the transformation
    original_size = Path(input_file).stat().st_size
    fixed_size = Path(output_file).stat().st_size
    print(f"Original size: {original_size:,} bytes")
    print(f"Fixed size: {fixed_size:,} bytes")
    print(f"Ready for APIM import!")

def main() -> None:
    """Main entry point for the Azure OpenAI spec fixer.
    
    Downloads the latest Azure OpenAI specification and applies all necessary
    transformations for Azure APIM compatibility.
    """
    # Create argument parser for command-line flexibility
    parser = argparse.ArgumentParser(
        description="Downloads and fixes an Azure OpenAI spec for APIM compatibility.",
        epilog="Example:\n"
               "  python fix_openai_spec.py\n"
               "  python fix_openai_spec.py --url https://.../.../2025-05-01-preview/inference.json\n"
               "  python fix_openai_spec.py --output my_fixed_spec.json",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # Default URL is the latest preview version
    default_url = ("https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/"
                   "specification/cognitiveservices/data-plane/AzureOpenAI/inference/"
                   "preview/2025-04-01-preview/inference.json")
    
    parser.add_argument(
        '-u', '--url',
        type=str,
        default=default_url,
        help="URL of the Azure OpenAI spec to fix (defaults to 2025-04-01-preview)"
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default="inference_fixed.json",
        help="Output filename for the fixed spec (default: inference_fixed.json)"
    )
    
    parser.add_argument(
        '-k', '--keep-downloaded',
        action='store_true',
        help="Keep the downloaded original spec file (default: delete after processing)"
    )
    
    args = parser.parse_args()
    
    # Use command-line arguments or defaults
    spec_url = args.url
    fixed_file = args.output
    
    # Use a temp name for downloaded file to avoid conflicts
    original_file = "inference_downloaded.json"
    
    # Construct base URI for resolving relative external file references
    spec_base_uri = "/".join(spec_url.split("/")[:-1]) + "/"
    
    try:
        # Step 1: Download the latest specification
        download_spec(spec_url, original_file)
        
        # Step 2: Apply all APIM compatibility fixes
        fix_openapi_spec(original_file, fixed_file, spec_base_uri)
        
        # Success message with next steps
        print(f"\nSuccess! Use {fixed_file} in your APIM import.")
        print(f"The fixed specification is ready at: {Path(fixed_file).absolute()}")
        
        # Clean up downloaded file unless user wants to keep it
        if not args.keep_downloaded:
            Path(original_file).unlink(missing_ok=True)
            print(f"Cleaned up temporary file: {original_file}")
        
    except requests.RequestException as e:
        print(f"Network error downloading spec: {e}")
        print("Check your internet connection and try again.")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in downloaded spec: {e}")
        print("The source specification may be malformed.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        print("Please report this issue with the full error details.")

if __name__ == "__main__":
    main()
