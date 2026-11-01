# Attribution - istqb-testing

## Sources

This single package has two sources, kept distinct by the routing in SKILL.md:

### Source 1: Foundation Level syllabus structure

- **Syllabus:** ISTQB Certified Tester Foundation Level (CTFL) Syllabus, version 4.0.1, dated 15 September 2024, a maintenance revision of version 4.0, released 21 April 2023.
- **Owner:** International Software Testing Qualifications Board (ISTQB). ISTQB is a registered trademark of that board.
- **Structure used:** the six syllabus chapters, their section headings, and their learning objective topics, as listed in the official syllabus table of contents.
- **How it was produced:** no book or file was supplied by the user for the Foundation part. The chapter map was verified against the official syllabus table of contents, and notes were written chapter by chapter into `workspace/istqb-notes/notes-ch01.md` through `notes-ch06.md` before that part was built.

### Source 2: Test Analyst book, supplied by the user

- **Title:** Practical Software Test Analysis: A Self-Study Companion for the ISTQB Test Analyst Exam
- **Authors:** Adam Roman and Matthias Hamburg
- **Publisher:** Springer Nature Switzerland, 2026
- **ISBN:** 978-3-032-27986-6
- **How it was produced:** the user supplied their own EPUB copy. The EPUB text was extracted chapter by chapter into working files under `workspace/psta-notes/extracted/`, then seven chapter readers produced paraphrased study notes into `workspace/psta-notes/notes-intro.md`, `notes-ch01.md` through `notes-ch05.md`, and `notes-answers.md`. This package was distilled from those notes by the main agent, not by the readers.
- **What is not in this package:** the book's sample questions, exercises, figures, tables, and case study are not reproduced. Practice prompts in this package are original, modelled on the book's technique types, not copied from its questions.

## How the content was produced, for both sources

- All explanations, definitions, and examples in this package are paraphrased summaries written in the distiller's own words. No passages of syllabus body text or book body text are reproduced.
- Short syllabus terms, chapter and section titles, technique names, and numeric facts are carried over as factual data, because the terms and numbers are the substance of the subject. Numeric facts include, for CTFL, 40 questions, 60 minutes, 26 correct to pass, and the chapter split (Chapter 1: 8, Chapter 2: 6, Chapter 3: 4, Chapter 4: 11, Chapter 5: 9, Chapter 6: 2). For Test Analyst, the book presents 45 questions, 120 minutes, 78 points maximum, and 51 points to pass, with Chapter 3 carrying the largest share. Confirm both against your exam provider before booking, because exam versions can differ by language and provider, and the book itself flags a wording conflict on the Test Analyst syllabus version date.
- All worked examples are original. The Foundation running examples are a library age rule, a shop discount rule, an order lifecycle, and a shop checkout. The Test Analyst running examples use a library system, a clinic booking system, and a shop, in original scenarios. None of them is taken from the syllabus, the book's case study, or an official sample exam.
- This package contains no links to outside sources and needs no outside page to be used. That is deliberate: the user instruction for skill packages in this set is that a package must be self-sufficient, with all details and examples inside the package itself.
- Known gaps are stated in the references, not smoothed over: several book techniques depend on figures and tables that are not recoverable from extracted text alone, so those techniques are covered in general form with original examples, and exam preparation for figure-dependent questions should use the original book with its figures in front of you. One exercise solution in the book appears internally inconsistent in its closing summary; the table-driven risk changes are the reliable part, and the skill does not quote that closing summary as a conclusion.

## Rights

- All rights in the original syllabus remain with ISTQB and its authors. All rights in the book remain with its authors and Springer Nature Switzerland.
- This package is an unofficial personal study aid. It is not accredited by ISTQB, not endorsed by ISTQB, and not a substitute for the official syllabus or the book.
- **No license grant:** nothing in the source material grants a license to redistribute the syllabus, the book, or derivative copies of their text. Treat this package as private study material, not published or sold.
- If you are preparing for either exam, obtain the current official syllabus and official sample exams from ISTQB or your local member board, and confirm the syllabus version your exam uses.
- The previous Foundation-only package, `istqb-foundation-testing`, is superseded by this merged package and should not be distributed alongside it.
