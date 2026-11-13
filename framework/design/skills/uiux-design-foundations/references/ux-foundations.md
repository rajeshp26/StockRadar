# UX Foundations — Process and Structure from From Zero to UI/UX Hero!

Paraphrased digest of the book's process chapters (chapters 8, 9, 11, 12, 13, plus the testing material). The laws and advanced theory live in ux-laws.md. Page numbers are PDF pages of the user-supplied copy.

## What UX design is (pp. 56–58)
- UX design covers every aspect of the end-user's interaction with the company, its services, and its products, from physical feel to the simplicity of a checkout flow (Don Norman's framing).
- Aim for interactions that are easy, efficient, relevant, and enjoyable.
- UX work rests on research and testing into habits, preferences, and behaviour, and spans strategy, product development, design, and testing, not visuals alone.
- Good UX is often invisible; its absence is what users notice. Hidden buttons, excessive pop-ups, and convoluted processes frustrate users and send them to competitors. The book's positive example is a maps product praised for a seamless interface, easy-to-understand directions, and real-time updates.
- A concrete hierarchy illustration the book uses at the Part Two divider: four equal-weight buttons redesigned into one prominent primary button (with a count badge) plus de-emphasised icon actions.
- Business case: smooth experiences convert first-time users into loyal customers, and bad design ultimately costs more than good design (a point the book attributes to Dr Ralf Speth, CEO of Jaguar Land Rover). The book's lead commercial example is a website redesign credited with increasing bookings at Airbnb.

## User research (pp. 59–61)
- Research gathers insight into what drives users, so decisions rest on evidence about preferences and behaviour. The framing the book borrows from Don Norman: a great product starts with understanding the people who will use it.
- Six methods:
  1. In-depth interviews: one-to-one, open-ended questions; surface experiences, motivations, pain points; listen actively and note recurring themes.
  2. Observational studies: watch users in their real environment; note behaviour and difficulties; surfaces problems users do not realise they have.
  3. Surveys: reach many users with concise mixed questions; good for quantitative data and trends; pair with other methods for the full story.
  4. Focus groups: moderated group discussion; rich dynamics, but beware groupthink and dominant voices.
  5. Card sorting: users organise content into categories that make sense to them; informs navigation and information architecture.
  6. Usability testing: users attempt realistic tasks while observed; reveals issues other methods miss.
- Always analyse for patterns and trends, and keep stakeholders in the loop; research is a team effort.

## Personas (pp. 61–63)
- A persona represents one audience segment: its traits, challenges, and motivations.
- Five steps: analyse research for patterns; identify key characteristics (demographics, goals, motivations, frustrations, tech-savviness) without stereotyping; give the persona a name and a face to build team empathy; write a backstory covering life, experiences, hobbies, work, family, and product interaction; share with the team and stakeholders for feedback.
- Worked example: the book's sample persona is a 35-year-old software engineer, and it fixes the field format a persona carries: name, age, occupation, traits, frustrations, and a goal the product serves.
- Tool options by detail level: documents (Word, Google Docs) for simple personas; slides (PowerPoint, Google Slides) for one persona per slide; design tools (Illustrator, Canva, Figma) for polished layouts; specialised tools (Xtensio, UserForge) for templates and collaboration.

## Information architecture (pp. 84–85)
- IA is organising, structuring, and labelling content so users can find information and complete tasks, understanding the overall structure and how elements connect.
- Peter Morville's framing: good IA helps users understand where they are, what they have found, what is around them, and what to expect.
- IA shapes content strategy and wording, and influences UI and interaction design during wireframing and prototyping.
- Four components (Rosenfeld and Morville): organisational frameworks and structures (how content is categorised), representation systems (how it is depicted), navigational mechanisms (how users browse), discovery systems (how users search).
- Information ecology: IA sits at the intersection of context (business goals, funding, politics, culture, technology, resources, constraints), content (goals, types, volume, existing structures, governance, ownership), and users (audience, tasks, needs, information-seeking behaviour, experience). All three must be weighed together.

## Goals and competitor analysis (pp. 85–87)
- Define clear goals and analyse competitors before any design or code work.
- Purposes: judge market position, find gaps, learn competitors' strengths and weaknesses, gather evidence for design changes, help resolve usability issues, and inform product strategy.
- Process: define the goal and the purpose of the analysis; list direct competitors (same offer, similar price) and indirect ones (different offer, same need); build a feature comparison chart (interface, imagery, filters, sorting, load time, responsiveness); present findings visually.
- Frameworks named: SWOT analysis (internal and external factors), BCG Growth-Share Matrix (market share against growth: Dogs, Cash Cows, Stars, Question Marks), Porter's Five Forces (buyers, suppliers, substitutes, rivalry, new entrants), perceptual mapping (how customers perceive products against competitors).
- Principle: understand competitors, do not copy them. Learn from their successes and avoid their pitfalls.

## Organising content and navigation (pp. 88–89)
- Content audit first: review existing content and media systematically to find gaps, redundancies, and inconsistencies, then decide what to keep, revise, or remove.
- Card sorting method: put each content item on its own card (physical or online tool); recruit target-profile users to group them; ask participants to name each group; analyse patterns across sorts to shape the IA; repeat as the product evolves, never treat it as one-off.
- Navigation rule: a good system makes it obvious where users are, where they can go, and how to get back. Navigation is core UX, not just a menu or a list of links.
- Test and refine navigation with real users, iteratively.

## Testing and evaluating (pp. 89–90)
- Usability testing: evaluate with real users, from informal think-aloud observation to structured sessions with defined tasks, success criteria, and a facilitator. Goals: find usability problems, gather qualitative and quantitative data, judge satisfaction.
- User acceptance testing (UAT): the final phase, end users in real-world scenarios, validating readiness and that user and business requirements are met.
- A/B testing: two versions of one element, users split randomly, behaviour compared for a data-driven choice.
- Other methods named: heatmap analysis, first-click testing, eye-tracking studies. Pick by product, users, and stage.
- Testing is continuous, not one-time, because users, competitors, and technology change.

## Tools and techniques (pp. 91–92)
- Sketching and wireframing: pen and paper for fast iteration; wireframes define page structure and layout.
- Prototyping tools named: Sketch, Figma, Adobe XD, for interactive mockups, sharing, and testing.
- Testing platforms named: UsabilityHub, UserTesting, Lookback, for running tests, live feedback, recordings, and analysis.
- Collaboration and handoff tools named: Zeplin, InVision Inspect, for specs, assets, and code snippets.
- Analytics tools named (post-launch): Google Analytics, Hotjar, Mixpanel, for behaviour, pain points, and optimisation.
- Techniques named: card sorting, journey mapping, heuristic evaluation.
- Caution: tools are instruments only. Quality comes from understanding user needs, creativity, and problem-solving, not from the tool.

## Working with developers (pp. 92–94)
- Involve developers early, not only at handoff, to surface infeasible ideas before the final stage and build shared ownership.
- Understand their world: designers need a basic grasp of what developers do, their constraints, and their terminology, not deep coding expertise.
- Be open to feedback: developer review is a second perspective that catches issues the designer missed.
- Bridging the gap is cultural: build a shared language and mutual understanding instead of throwing prototypes over a wall. The two disciplines think differently (aesthetics and UX against functionality), which is productive once vocabulary is shared.
- Use Figma as the shared cloud workspace: designers build there; developers inspect, export assets, and pull code snippets (CSS, with the older Android XML format noted as somewhat outdated), reducing back-and-forth.
- Use style guides and design systems to define typography, colours, components, and patterns so developers can reproduce the design accurately and consistently.
- Hold frequent check-ins to discuss progress, share ideas, clear blockers, and align early; late changes are harder and costlier.
- Build cross-discipline empathy: designers learn basic coding constraints; developers learn design principles and usability.

## Concept design and brainstorming (pp. 96–105)

### Moodboards (pp. 96–97)
- A moodboard is a curated collage of images, colours, textures, and design elements that sets the intended mood and style and acts as a visual compass before design proper begins. It also gives stakeholders an early preview, so the team aligns before design proper starts.
- Typical size: about 8 to 15 images, drawn from fields such as graphic design, nature photography, architecture, and illustration. Keep a consistent style with no contradictions, add a written description for client transparency, and avoid lifting images from other websites to protect originality.
- Present two different moodboards for the client to choose between; weaving the client's own brand into the board lands well.
- Collect across categories: typography (at least 3 examples, including type inside a layout), colour (palettes that carry the target mood), aesthetics (photos and illustration capturing the feel), grid and layout (compelling organisation examples), animations when motion is required (references such as Awwwards), and shapes (geometric or organic building blocks).
- Quality over quantity; gathering can take 2 to 4 days on some projects. Sources named: Savee, Pinterest, Typographic Posters, Behance, Unsplash, Instagram, Freepik, Awwwards, 500px.

### Sketching and prototyping (pp. 98–99)
- Sketch before going digital: fast, simple, rapid iteration; artistic skill is not required, since sketches communicate ideas (stick figures and basic shapes are fine).
- A practical prototyping start: open a blank 1920x1080 frame in Figma, drop in all needed content without organising it, then shuffle and sort it into a structured layout.
- Fidelity: low-fidelity (wireframes) foregrounds function and layout and wins early feedback fast; high-fidelity mimics the final look and interactivity, costs more, and suits usability testing.
- The process is iterative: sketch, prototype, gather feedback, refine, repeat. Aim for consistent improvement, not instant perfection.

### Wireframing (pp. 101–104)
- A wireframe is the blueprint of a page: structure, layout, information architecture, user flow, functionality, and intended behaviour, with the hierarchy of text, images, navigation, and calls to action.
- Three types: low-fidelity (quick, often hand-drawn, basic layout only), mid-fidelity (more detailed structure, still room to change), high-fidelity (detailed, may include interaction specifics, closest to final; good for user testing and stakeholder communication).
- The colour-free, simplified form makes structure and function easier to judge, and helps designers, developers, researchers, and investors reach consensus before building.
- Learning path the book gives: understand the basics, learn the types and when each applies, study existing wireframes, choose a tool (Sketch, Adobe XD, Figma, Balsamiq, Axure RP named), practise from paper into the tool, get feedback, keep learning (Coursera, Udemy, LinkedIn Learning, Skillshare named), and join design challenges (Dribbble, Behance named).

### Evaluating and refining (pp. 104–105)
- Step back from attachment to your own ideas and judge the work by its prototype.
- Three evaluation questions: does the solution fulfil its purpose; does it align with the user needs found earlier; is it feasible within time, budget, and technology.
- Use the answers to find strengths and weaknesses, then refine (adjust colours, fix an unintuitive layout) and test every iteration, because user testing reveals what the designer's perspective cannot.
- Stay flexible: discarding what does not work is expected in an iterative process.
