# 51_MODULE_TEMPLATE.md

## Purpose
This document defines the Module Template for JARVIS OS. It establishes the code skeletons, directory structure, imports, and interface formatting rules that developers and agents must use when initializing a new Python or Next.js module.

## Scope
Applies to all new backend sub-packages in `core/` and frontend folders in `frontend/`.

## Module Code Templates

### 1. Python Module Skeleton (`module_name.py`)
```python
"""
Purpose: Brief description of the module.
Responsibilities: Single sentence module responsibilities list.
Dependencies: list of imported libraries.
"""
from typing import Dict, Any
from jarvis.core.logger import get_logger
from jarvis.core.exceptions import JarvisValidationError

logger = get_logger(__name__)

class JarvisModule:
    """Core module container enforcing SRP."""
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        logger.info("Initializing module")

    async def execute_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point enforcing structured validation."""
        if not payload:
            raise JarvisValidationError("Payload cannot be empty")
        # Implementation goes here
        return {"status": "success", "result": {}}
```

### 2. Next.js Component Skeleton (`ComponentName.tsx`)
```typescript
import React from 'react';

interface ComponentProps {
  title: string;
  isActive: boolean;
}

export const ComponentName: React.FC<ComponentProps> = ({ title, isActive }) => {
  return (
    <div className={`p-4 rounded-lg ${isActive ? 'bg-blue-600' : 'bg-gray-800'}`}>
      <h2 className="text-xl font-bold text-white">{title}</h2>
    </div>
  );
};
```

## Responsibilities
- **Developer Agent:** Instantiates code files matching these skeletons.
- **Reviewer Agent:** Rejects pull requests that deviate from these template files.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 8, Rule 10, and Rule 11).

## Interfaces
- Code generation tools in the core Brain package.

## Examples
- **Correct Module Design:** Creating `core/memory/vector_client.py` matching the initialization, type annotations, and error wrappers from this template.
- **Incorrect Module Design:** Writing a helper script containing raw code lines, no class wrappers, and no error checks. (Violates PEP 8, Typings, and Module standards).

## Failure Cases
- **Template Drift:** An agent generates a module without typing or documentation headers. *Mitigation:* The Quality Gates compile files and raise validation warnings if docstrings or type signatures are missing.

## Security Considerations
- Skeletons force initialization of logger variables with trace logging context to ensure all action operations are observable.

## Future Extension
- Template updates are logged in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md)
- [50_FEATURE_TEMPLATE.md](file:///e:/jarvis/docs/50_FEATURE_TEMPLATE.md)
