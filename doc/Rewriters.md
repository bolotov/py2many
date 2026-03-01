

Certain things are supported only in certain languages.
Rewriters fix that as a **post-processing** step of transpile process.
 
How things are now - cli does post-processing based on conditions hard-coded
into rewriters themselves

How it should be - **target** language must describe which rewriters it
needs and **how** they must be applied

 
 - with statement rewriting is only needed in languages that
  don't support with statements, so it's only applied to those languages.
  
 - IgnoredAssignRewriter is only applied to languages that don't support
  ignored variables in destructuring assignments, since in those languages
  we need to rewrite those assignments to avoid syntax errors. In languages
  that do support ignored variables, we can keep the original destructuring
  assignments, which are more concise and readable.
  
 - fstring rewriting is only applied to languages that don't support fstrings.
 This is done to avoid unnecessary rewrites that can make the output code less
 readable and much more verbose, while still making it compatible with
 the target language.
 
 By only applying the rewrites that are necessary for the target language,
 we can keep the output code cleaner and more readable, while still ensuring
 that it can be transpiled to the target language without issues.

---


IDEAS (TODO):
- maybe have a type/class 'language' and backend would be requered to
  have itself described using it in code of targets/backends in __init__i
  regarding which rewriters does it need and how it needs them or to have
  own rewriters with own stuf or with customized standard rewriters

- maybe have a separate rewriter for each language that inherits from
  a common base class and overrides the methods that need to be different?

- or a functional way to have type of language to be inherited from 
  a template but defined in a **target** language folder

