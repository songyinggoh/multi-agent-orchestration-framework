# Plan Skill

## Description
Research-driven implementation planning skill that follows a rigorous workflow: Research → Plan → Track → Execute with TDD.

## When to Use
- Before implementing any new feature
- When solving complex problems
- When fixing non-trivial bugs
- Any task requiring architectural decisions

## Workflow

### Phase 1: Research (MANDATORY)

1. **Codebase Research**
   - Search for existing patterns and similar implementations
   - Identify relevant files, functions, and modules
   - Extract code snippets that demonstrate current patterns
   - Note file paths for all relevant files

2. **Web Research** (if needed)
   - Search official documentation (prioritize 2026+ content)
   - Look for best practices and common pitfalls
   - Check for breaking changes in dependencies
   - Find relevant code examples and patterns

3. **First-Principles Thinking**
   - Break down the problem into fundamental components
   - Identify 3-5 solution vectors
   - For each solution, evaluate:
     - **Pros/Cons**: Trade-offs and implications
     - **Complexity**: Implementation difficulty (Low/Medium/High)
     - **Cost**: Resource requirements (time, compute, dependencies)
     - **Time**: Estimated effort (Quick/Medium/Extended)
     - **Fit Score**: Alignment with codebase (1-10)
     - **Code Snippet**: Example implementation
     - **Files to Modify**: Specific file paths

4. **Export Research Document**
   - Location: `docs/research/[TOPIC_NAME]_Research.md`
   - Format:
     ```markdown
     # [Topic Name] Research
     **Date**: YYYY-MM-DD
     **Author**: Claude Code
     **Status**: Complete

     ## Problem Statement
     [Clear description of the problem to solve]

     ## Current State Analysis
     [What exists in the codebase now]

     ### Relevant Files
     - `path/to/file1.ts` - [Purpose]
     - `path/to/file2.ts` - [Purpose]

     ### Current Patterns
     ```language
     // Code snippet showing current pattern
     ```

     ## Solution Vectors Evaluated

     ### Solution 1: [Name]
     **Fit Score**: X/10

     **Pros**:
     - [Advantage 1]
     - [Advantage 2]

     **Cons**:
     - [Disadvantage 1]
     - [Disadvantage 2]

     **Complexity**: Low/Medium/High
     **Cost**: [Resources needed]
     **Time**: Quick/Medium/Extended

     **Code Snippet**:
     ```language
     // Implementation example
     ```

     **Files to Create/Modify**:
     - `path/to/new/file.ts` - [Purpose]
     - `path/to/existing/file.ts` - [Changes needed]

     [Repeat for Solutions 2-5]

     ## Recommended Approach
     [Which solution and why]

     ## Strategic Evaluation
     - **Goals Alignment**: [How it aligns with project goals]
     - **Economic Value**: [Business impact]
     - **Implementation Feasibility**: [Technical feasibility]
     - **Risk Assessment**: [Potential risks and mitigations]

     ## Dependencies
     [External libraries, APIs, services needed]

     ## References
     - [Documentation links]
     - [Tutorial/blog links]
     - [Stack Overflow/GitHub issues]
     ```

### Phase 2: Implementation Planning

1. **Read Context Documents**
   - `CLAUDE.md` (if exists)
   - `README.md` (if exists)
   - Any architecture docs in `docs/`
   - Existing implementation plans

2. **Create Implementation Plan**
   - Location: `docs/implementation-plan/[FEATURE_NAME]_Implementation_Plan.md`
   - Format:
     ```markdown
     # [Feature Name] Implementation Plan
     **Date**: YYYY-MM-DD
     **Based on Research**: [Link to research doc]
     **Status**: Not Started

     ## Overview
     - **Objective**: [What we're building]
     - **Value**: [Why it matters]
     - **Affected Components**: [Which parts of the system]

     ## Research Summary
     - **Selected Approach**: [Solution name from research]
     - **Key Trade-offs**: [What we're optimizing for]
     - **Dependencies**: [External requirements]

     ## Implementation Strategy

     ### Phase 1: [Foundation/Setup/Core]
     **Goal**: [What this phase achieves]

     **Tasks**:
     1. [ ] Task 1.1 - [Description]
        - File: `path/to/file.ts`
        - Code snippet:
          ```typescript
          // Example of what to implement
          ```

     2. [ ] Task 1.2 - [Description]
        - Files: `path/to/file1.ts`, `path/to/file2.ts`

     **Test Specifications**:
     - Unit Tests:
       - [ ] Test case 1
       - [ ] Test case 2
     - Integration Tests:
       - [ ] Integration scenario 1

     **Files to Create**:
     - `src/services/new-service.ts` - [Purpose]

     **Files to Modify**:
     - `src/app.ts` - [Changes needed]

     ### Phase 2: [Integration/Enhancement]
     [Same structure as Phase 1]

     ### Phase 3: [Testing/Documentation]
     [Same structure as Phase 1]

     ## Success Metrics
     - **Technical**:
       - Test coverage >= 80%
       - 0 TypeScript errors
       - 0 lint errors
       - All quality gates passing

     - **Business**:
       - [KPI 1]: [Target]
       - [KPI 2]: [Target]

     ## Quality Gates
     - [ ] All unit tests passing
     - [ ] All integration tests passing
     - [ ] Coverage >= 80%
     - [ ] TypeScript compilation successful
     - [ ] Lint passing
     - [ ] No `any` types in new code

     ## Rollback Plan
     [How to revert if something goes wrong]

     ## Future Enhancements
     - [Potential improvement 1]
     - [Potential improvement 2]
     ```

3. **Create Progress Tracker**
   - Location: `docs/implementation-plan/[FEATURE_NAME]_PROGRESS.md`
   - Format:
     ```markdown
     # [Feature Name] - Progress Tracker
     **Status**: 0% Complete
     **Last Updated**: YYYY-MM-DD HH:MM
     **Implementation Plan**: [Link to implementation plan]

     ## Progress Overview
     - Phase 1: Not Started (0/X tasks)
     - Phase 2: Not Started (0/X tasks)
     - Phase 3: Not Started (0/X tasks)

     ## To-Do List

     ### Phase 1: [Name]
     - [ ] Task 1.1 - [Description] (`file.ts:123`)
     - [ ] Task 1.2 - [Description] (`file.ts:456`)

     ### Phase 2: [Name]
     - [ ] Task 2.1 - [Description]
     - [ ] Task 2.2 - [Description]

     ## Current Blockers
     [None / List blockers]

     ## Next Actions
     1. [Next immediate step]
     2. [Following step]

     ## Completed Tasks Log
     [Empty initially, updated as tasks complete]

     ## Quality Gate Status
     - [ ] Tests: Not Run
     - [ ] Coverage: Not Measured
     - [ ] Lint: Not Run
     - [ ] Type Check: Not Run

     ## Notes
     [Implementation notes, decisions made, issues encountered]
     ```

### Phase 3: Approval & Execution

1. **Present Plan to User**
   - Summarize the research findings
   - Highlight the recommended approach
   - Explain the implementation strategy
   - Wait for explicit approval

2. **DO NOT PROCEED** until user approves

3. **After Approval: TDD Implementation**
   - Follow RED -> GREEN -> REFACTOR -> QUALITY GATE cycle
   - Update progress tracker after each task
   - Run quality gates before each commit

### Phase 4: Quality Verification

1. **Pre-Commit Checklist**:
   ```bash
   # Run lint
   npm run lint              # 0 errors

   # Run type checking
   npm run type-check        # 0 errors

   # Run tests
   npm run test              # All passing

   # Run coverage (if configured)
   npm run test:coverage     # >= 80%
   ```

2. **Update Documentation**:
   - Mark progress tracker as Complete
   - Update implementation plan with completion notes
   - Add any learnings to research document

## Skill Invocation

When user types `/plan [topic]`:
1. Start with research phase
2. Create research document in `docs/research/`
3. Create implementation plan in `docs/implementation-plan/`
4. Create progress tracker in `docs/implementation-plan/`
5. Present findings and wait for approval
6. After approval, begin TDD implementation

## Examples

### Example 1: New Feature
```
User: /plan add authentication with JWT

Claude:
1. Researches JWT patterns in codebase
2. Checks existing auth setup
3. Searches for best practices (2026 docs)
4. Creates: docs/research/JWT_Auth_Research.md
5. Creates: docs/implementation-plan/JWT_Auth_Implementation_Plan.md
6. Creates: docs/implementation-plan/JWT_Auth_PROGRESS.md
7. Presents plan for approval
```

### Example 2: Bug Fix
```
User: /plan fix WebSocket connection dropping

Claude:
1. Researches WebSocket code in src/
2. Identifies 3-5 potential solutions
3. Creates: docs/research/Bug_Fix_WebSocket_Research.md
4. Creates: docs/implementation-plan/Fix_WebSocket_Plan.md
5. Creates: docs/implementation-plan/Fix_WebSocket_PROGRESS.md
6. Presents findings and recommended fix
```

## Notes

- Always create the directories if they don't exist
- Use descriptive, PascalCase file names with underscores
- Include timestamps in all documents
- Reference specific file paths and line numbers when possible
- Extract real code snippets from the codebase
- Update progress tracker immediately after completing tasks
- Never skip the research phase
- Always wait for user approval before implementing
