# Azure OpenAI APIM Compatibility Fix

A Python script that fixes Azure OpenAI API specification files for successful import into Azure API Management (APIM), enabling GPT-5 model access and new Azure OpenAI features through your APIM gateway.

## Problem Statement

The Azure OpenAI 2025-04-01-preview specification uses OpenAPI 3.1.0 format with external file references and features that cause import failures in Azure API Management. This specification is required to access GPT-5 models and new Azure OpenAI endpoints like `/responses` through APIM. 

### Common APIM Import Errors

When importing the raw Azure OpenAI specification, you may encounter these errors:

```
One or more fields contain incorrect values:
Parsing error(s): Cannot create a scalar value from this type of node. [#/components/schemas/createResponse/allOf/properties/include/description]
Parsing error(s): The input OpenAPI file is not valid for the OpenAPI specification https://github.com/OAI/OpenAPI-Specification/blob/master/versions/3.1.1.md (schema https://github.com/OAI/OpenAPI-Specification/blob/master/schemas/v3.1/schema.yaml).
```

This tool transforms the specification to be APIM-compatible while preserving functionality and resolving all these import errors.

See related issue: [Azure/azure-rest-api-specs#35062](https://github.com/Azure/azure-rest-api-specs/issues/35062)

## What This Script Does

### Transformations Applied

1. **External Reference Bundling**
   - Resolves all external file references (`$ref` pointing to other files)
   - Creates a single, self-contained specification file
   - Preserves internal references (`#/components/schemas/...`) to maintain a small file size as they are valid in OpenAPI

2. **Compatibility Fixes**
   - Removes OpenAPI 3.1.0-specific keywords not supported by APIM:
     - `$recursiveRef` 
     - `$recursiveAnchor`
     - `propertyNames`
   - Converts complex description objects to strings
   - Fixes discriminator properties by adding required fields to polymorphic schemas

3. **Version Handling**
   - Preserves OpenAPI 3.1.0 version (APIM accepts 3.1.0 but automatically rewrites to 3.0.1)
   - APIM handles any necessary version conversion internally

## Installation

### Prerequisites

- Python 3.7 or higher

### Setup

1. Clone or download this repository:
```bash
git clone https://github.com/jmottishaw/azure-openai-apim-fix.git
cd azure-openai-apim-fix
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

Required packages:
- `requests` - For downloading specifications
- `jsonref` - For resolving JSON references

## Usage

### Basic Usage

Run with default settings (downloads and fixes the latest 2025-04-01-preview specification):

```bash
python fix_openai_spec.py
```

This will:
- Download the latest Azure OpenAI specification with GPT-5 model support
- Apply all necessary fixes for APIM compatibility
- Output `inference_fixed.json` ready for APIM import

### Command-Line Options

```bash
python fix_openai_spec.py [OPTIONS]

Options:
  -h, --help            Show help message and exit
  -u URL, --url URL     URL of the Azure OpenAI spec to fix 
                        (defaults to 2025-04-01-preview)
  -o OUTPUT, --output OUTPUT
                        Output filename for the fixed spec 
                        (default: inference_fixed.json)
  -k, --keep-downloaded Keep the downloaded original spec file 
                        (default: delete after processing)
```

### Examples

Fix a specific version:
```bash
python fix_openai_spec.py --url https://raw.githubusercontent.com/Azure/azure-rest-api-specs/main/specification/cognitiveservices/data-plane/AzureOpenAI/inference/preview/2025-05-01-preview/inference.json
```

Custom output filename:
```bash
python fix_openai_spec.py --output my_fixed_spec.json
```

Keep the downloaded file for inspection:
```bash
python fix_openai_spec.py --keep-downloaded
```

## APIM Import Instructions

#### Required: Update Server URLs

Before importing, you must update the server URL in the fixed specification to match your APIM endpoint.

The original specification uses a variable server URL pattern:
```json
"servers": [
  {
    "url": "https://{endpoint}/openai",
    "variables": {
      "endpoint": {
        "default": "your-resource-name.openai.azure.com"
      }
    }
  }
]
```

I just removed the variables section completely and update the url:
```json
"servers": [
  {
    "url": "https://your-apim-endpoint.com/openai"
  }
]
```

### 2. Update APIM Inbound Processing Rules (If Needed)

**Note:** The new specification includes new endpoints like `/responses` that may require updates to your APIM inbound processing policy, depending on your current configuration. If you're only using traditional endpoints like `/chat/completions`, no policy changes may be needed.

## How It Works

### Technical Details

1. **Downloads** the OpenAPI specification from Azure's GitHub repository
2. **Resolves** external file references using the `jsonref` library while preserving internal references
3. **Identifies and fixes** compatibility issues:
   - Complex description objects are converted to JSON strings
   - Discriminator properties are added to required fields
   - Unsupported OpenAPI 3.1.0 keywords are removed
4. **Outputs** a clean, APIM-compatible specification

### File Structure

- `fix_openai_spec.py` - Main script
- `requirements.txt` - Python dependencies
- `README.md` - This documentation
- `inference_fixed.json` - Output file (generated)

## Tested Compatibility

- **Tested with**: Azure OpenAI API 2025-04-01-preview
- **APIM Version**: Latest Azure API Management (stv2)
- **Python**: 3.12.13
- **Status**: Successfully imported and tested in production APIM environments

## License

This tool is provided as-is for the community to resolve Azure OpenAI APIM import issues.

## Version History

- **1.0.0** - Initial release supporting 2025-04-01-preview specification
  - Bundles external references
  - Fixes discriminator properties
  - Removes unsupported OpenAPI 3.1.0 keywords
  - Preserves OpenAPI 3.1.0 version (APIM now supports it)
