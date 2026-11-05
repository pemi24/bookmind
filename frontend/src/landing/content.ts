/**
 * Every word on the public landing page. Edit copy here; the components only lay it out.
 *
 * - Icons are names from the ICONS map in `ui/Icon.tsx` (lucide icons).
 * - Links: "#/signup" and "#/login" open the sign-up / sign-in forms; "#features" style anchors
 *   scroll to a section (ids below); "#/privacy" and "#/terms" are the legal pages.
 * - Book quotes in the demos are from public-domain books, quoted exactly.
 */

export type IconName =
  | "upload"
  | "message"
  | "headphones"
  | "book"
  | "sparkles"
  | "graduation"
  | "compass"
  | "folder"
  | "shield"
  | "file"
  | "quote"
  | "users"
  | "pen"
  | "search"
  | "timeline"
  | "eye-off"
  | "highlighter"
  | "layers"
  | "wifi-off"
  | "languages"
  | "lock"
  | "github"
  | "mail"
  | "rss";

export type Audience = "students" | "researchers" | "book-clubs" | "writers" | "lifelong-learners";

/* ---------- top of the page ---------- */

export const announcement = {
  id: "listening-2026-11", // change it to show a dismissed bar again
  label: "New",
  text: "Listen to any book in natural voices, with the sentence highlighted as it's read.",
  link: { label: "See listening mode", href: "#listen" },
};

export const nav = {
  links: [
    { label: "Features", href: "#features" },
    { label: "How it works", href: "#how-it-works" },
    { label: "Use cases", href: "#use-cases" },
    { label: "FAQ", href: "#faq" },
  ],
  login: { label: "Log in", href: "#/login" },
  cta: { label: "Get started free", href: "#/signup" },
};

/* ---------- hero ---------- */

export const hero = {
  eyebrow: "Your library, in conversation",
  headline: "Talk to any book.",
  sub: "Upload a book, ask it anything, and get answers that point to the exact page. Then sit back and listen to it read aloud.",
  primary: { label: "Get started free", href: "#/signup" },
  secondary: { label: "See how it works", href: "#how-it-works" },
  note: "Free and private. Runs on your own computer.",
};

export interface Citation {
  marker: number;
  where: string; // "Ch. 1 · Down the Rabbit-Hole"
  quote: string;
}

export interface DemoChat {
  book: { title: string; author: string };
  question: string;
  /** The answer, typed out; [n] markers become citation chips. */
  answer: string;
  citations: Citation[];
}

export const heroChat: DemoChat = {
  book: { title: "Alice's Adventures in Wonderland", author: "Lewis Carroll" },
  question: "Why does Alice follow the White Rabbit?",
  answer:
    "Curiosity, mostly. She is bored on the riverbank with a book that has no pictures [1], and a rabbit that checks a watch from its waistcoat-pocket is far too strange to ignore. So she runs after it, burning with curiosity [2].",
  citations: [
    {
      marker: 1,
      where: "Ch. 1 · Down the Rabbit-Hole",
      quote: "“and what is the use of a book,” thought Alice “without pictures or conversations?”",
    },
    { marker: 2, where: "Ch. 1 · Down the Rabbit-Hole", quote: "and burning with curiosity, she ran across the field after it" },
  ],
};

/* ---------- 01–03 ---------- */

export const pillars = [
  {
    icon: "upload" as IconName,
    title: "Upload any book",
    body: "PDF, EPUB, Word, text or Markdown, or pick a free classic from Project Gutenberg. BookMind reads every chapter so you don't have to start from scratch.",
  },
  {
    icon: "message" as IconName,
    title: "Ask anything, get cited answers",
    body: "Answers come only from the book, with numbered citations that open the exact passage. If the book doesn't say, BookMind tells you so.",
  },
  {
    icon: "headphones" as IconName,
    title: "Listen to it read aloud",
    body: "Natural voices read chapters and replies, highlighting each sentence. Pick up where you left off, even from your phone's lock screen.",
  },
];

/* ---------- see it in action ---------- */

export type DemoResult =
  | { kind: "summary"; title: string; points: string[] }
  | { kind: "quiz"; title: string; question: string; options: string[]; correct: number }
  | { kind: "quotes"; title: string; quotes: { text: string; where: string }[] }
  | { kind: "characters"; title: string; people: { name: string; note: string }[]; links: [number, number, string][] };

export interface ShowcaseTab {
  id: Audience;
  label: string;
  book: { title: string; author: string };
  ask: string;
  reply: string; // typed out above the result card
  result: DemoResult;
}

export const showcase = {
  id: "showcase",
  title: "See it in action",
  sub: "The same library, used five different ways.",
  tabs: [
    {
      id: "students",
      label: "Students",
      book: { title: "Frankenstein", author: "Mary Shelley" },
      ask: "Quiz me on the first four letters.",
      reply: "Here's a short quiz on Walton's letters. Answer, then check the passage it comes from.",
      result: {
        kind: "quiz",
        title: "Question 1 of 5",
        question: "Where is Robert Walton writing from in his first letter?",
        options: ["Geneva", "St. Petersburgh", "Ingolstadt", "London"],
        correct: 1,
      },
    },
    {
      id: "researchers",
      label: "Researchers",
      book: { title: "The Art of War", author: "Sun Tzu, tr. Lionel Giles" },
      ask: "Find every passage about deception, with locations.",
      reply: "Three passages speak to it directly. Each one opens in the reader at the exact spot.",
      result: {
        kind: "quotes",
        title: "Verbatim quotes",
        quotes: [
          { text: "All warfare is based on deception.", where: "Ch. I · Laying Plans" },
          { text: "Hold out baits to entice the enemy.", where: "Ch. I · Laying Plans" },
          { text: "Let your plans be dark and impenetrable as night", where: "Ch. VII · Manœuvring" },
        ],
      },
    },
    {
      id: "book-clubs",
      label: "Book clubs",
      book: { title: "Pride and Prejudice", author: "Jane Austen" },
      ask: "Summarize chapters 1–6 for tonight's meeting. No spoilers past chapter 6.",
      reply: "Here's where things stand at the end of chapter 6, with nothing from later on.",
      result: {
        kind: "summary",
        title: "Chapters 1–6 · spoiler guard on",
        points: [
          "Mrs. Bennet is set on marrying off her five daughters when wealthy Mr. Bingley arrives at Netherfield.",
          "At the assembly, Bingley is charmed by Jane; his friend Mr. Darcy offends Elizabeth.",
          "Charlotte Lucas warns that Jane should show her feelings more plainly.",
          "Darcy begins, against his will, to notice Elizabeth's “fine eyes”.",
        ],
      },
    },
    {
      id: "writers",
      label: "Writers",
      book: { title: "Pride and Prejudice", author: "Jane Austen" },
      ask: "Map the main characters and how they're connected.",
      reply: "The core of the story, drawn from the whole book. Tap a name to see where it appears.",
      result: {
        kind: "characters",
        title: "Character map",
        people: [
          { name: "Elizabeth", note: "second Bennet daughter" },
          { name: "Darcy", note: "wealthy, proud" },
          { name: "Jane", note: "eldest Bennet daughter" },
          { name: "Bingley", note: "Darcy's friend" },
          { name: "Wickham", note: "officer" },
        ],
        links: [
          [0, 1, "rivals"],
          [2, 3, "courtship"],
          [1, 3, "friends"],
          [0, 2, "sisters"],
          [4, 1, "grudge"],
        ],
      },
    },
    {
      id: "lifelong-learners",
      label: "Lifelong learners",
      book: { title: "Moby-Dick", author: "Herman Melville" },
      ask: "Explain the Cetology chapter simply. Why is it even there?",
      reply: "In plain words, using the “explain like I'm five” style, with the passages it's based on.",
      result: {
        kind: "summary",
        title: "Ch. 32 · Cetology, explained simply",
        points: [
          "Ishmael pauses the story to sort whales into groups, the way a scientist of his day might.",
          "He admits the job is huge and that his system will be incomplete.",
          "The chapter shows how hard it is to fully know the whale, a theme the whole book keeps returning to.",
        ],
      },
    },
  ] as ShowcaseTab[],
};

/* ---------- feature highlights (alternating rows) ---------- */

export type MockupName = "summary" | "flashcards" | "explorer" | "timeline" | "spoiler" | "notes" | "listen";

export const highlights = {
  id: "features",
  title: "Everything you need to really know a book",
  sub: "Every tool works from the book itself, so what you learn is what the author wrote.",
  rows: [
    {
      id: "summaries",
      mockup: "summary" as MockupName,
      eyebrow: "Summaries",
      title: "Chapter summaries at the length you want",
      body: "Short, medium or detailed, for one chapter or the whole book. Saved once made, so they're there next time.",
      bullets: ["Per chapter or whole book", "Three lengths", "Respects the spoiler guard"],
    },
    {
      id: "study",
      mockup: "flashcards" as MockupName,
      eyebrow: "Study mode",
      title: "Quizzes and flashcards that come from the text",
      body: "Multiple choice, true or false and short answers, scored as you go. Flashcards come back when you're about to forget them.",
      bullets: ["Generated from any chapter", "Spaced repetition, exportable to Anki", "Every question links to its source"],
    },
    {
      id: "explorer",
      mockup: "explorer" as MockupName,
      eyebrow: "Explorer",
      title: "Characters, places and ideas, mapped",
      body: "See who's who and how they connect in a novel, or the key concepts and how they relate in non-fiction.",
      bullets: ["Interactive relationship graph", "Every mention, one tap away", "Talk to a character"],
    },
    {
      id: "timeline",
      mockup: "timeline" as MockupName,
      eyebrow: "Timeline",
      title: "The story in order",
      body: "Key events laid out chapter by chapter, so long and winding books stay easy to follow.",
      bullets: ["Events with chapter references", "Jump to any moment in the reader"],
    },
    {
      id: "spoilers",
      mockup: "spoiler" as MockupName,
      eyebrow: "Spoiler guard",
      title: "Ask freely, without spoiling the ending",
      body: "Tell BookMind how far you've read, or let it follow your reading. Answers, summaries and quizzes stay behind that line.",
      bullets: ["Set a chapter, or follow your progress", "Applies to every feature"],
    },
    {
      id: "notes",
      mockup: "notes" as MockupName,
      eyebrow: "Notes & highlights",
      title: "Highlight, annotate and keep what matters",
      body: "Highlight passages in four colours, add your thoughts, and save the best answers. Bring in your Kindle highlights too.",
      bullets: ["Export to Markdown or PDF", "Import Kindle clippings", "Tags and search"],
    },
    {
      id: "listen",
      mockup: "listen" as MockupName,
      eyebrow: "Listening mode",
      title: "Listen, with every sentence highlighted",
      body: "Natural voices that run on your own computer, or your device's voices. Choose one for books and another for chat replies.",
      bullets: ["Skip by sentence, paragraph or chapter", "Sleep timer and lock-screen controls", "Continue listening where you stopped"],
    },
  ],
};

/* ---------- how it works ---------- */

export const howItWorks = {
  id: "how-it-works",
  title: "How it works",
  sub: "Three steps, and the first one takes about a minute.",
  steps: [
    { illustration: "upload", title: "Upload", body: "Drop in a PDF, EPUB or document, or choose a free classic. BookMind reads and indexes it." },
    { illustration: "ask", title: "Ask", body: "Ask questions in your own words. Every answer cites the passages it comes from." },
    { illustration: "learn", title: "Learn", body: "Summarize, quiz yourself, explore the characters, or just listen while you walk." },
  ] as { illustration: "upload" | "ask" | "learn"; title: string; body: string }[],
};

/* ---------- capabilities ---------- */

export const capabilities = {
  id: "capabilities",
  title: "What you can do",
  groups: [
    {
      icon: "sparkles" as IconName,
      title: "Understand",
      items: ["Cited answers from the book", "Explain like I'm five, or like an expert", "Side-by-side translation"],
    },
    {
      icon: "graduation" as IconName,
      title: "Study",
      items: ["Quizzes with scoring", "Flashcards with spaced repetition", "Essay outlines backed by quotes"],
    },
    { icon: "compass" as IconName, title: "Explore", items: ["Character and concept maps", "Timelines", "Compare two books"] },
    {
      icon: "headphones" as IconName,
      title: "Listen",
      items: ["Natural, offline voices", "Sentence-by-sentence highlighting", "Sleep timer, resume anywhere"],
    },
    { icon: "folder" as IconName, title: "Organize", items: ["Highlights and notes", "Kindle import", "Reading stats and streaks"] },
    {
      icon: "shield" as IconName,
      title: "Stay in control",
      items: ["Private accounts; nobody else sees your library", "Runs on your own computer", "Export everything, delete anytime"],
    },
  ],
};

/* ---------- use cases ---------- */

export const useCases = {
  id: "use-cases",
  title: "Made for the way you read",
  sub: "A few ideas to start with. Each one opens a free account.",
  filters: [
    { id: "all", label: "All" },
    { id: "students", label: "Students" },
    { id: "researchers", label: "Researchers" },
    { id: "book-clubs", label: "Book clubs" },
    { id: "writers", label: "Writers" },
    { id: "lifelong-learners", label: "Lifelong learners" },
  ] as { id: "all" | Audience; label: string }[],
  cards: [
    { title: "Revise for an exam", line: "Turn set chapters into quizzes and flashcards.", audiences: ["students"] },
    { title: "Write a better essay", line: "Get an outline with a counter-argument and quotes to back it.", audiences: ["students", "writers"] },
    { title: "Find the exact quote", line: "Every passage on a theme, verified word for word.", audiences: ["researchers", "writers"] },
    { title: "Compare two authors", line: "Ask the same question of two books, with citations from each.", audiences: ["researchers"] },
    { title: "Prepare tonight's discussion", line: "A spoiler-free recap up to the chapter everyone has read.", audiences: ["book-clubs"] },
    { title: "Settle a debate", line: "Who said it, and in which chapter? Look it up in seconds.", audiences: ["book-clubs", "lifelong-learners"] },
    { title: "Study a classic's craft", line: "Map characters and timelines to see how the story is built.", audiences: ["writers"] },
    { title: "Read in another language", line: "Follow a chapter side by side with a translation.", audiences: ["lifelong-learners", "students"] },
    { title: "Listen on your commute", line: "Pick up exactly where you stopped, from your phone.", audiences: ["lifelong-learners", "book-clubs"] },
    { title: "Talk to a character", line: "Ask Elizabeth Bennet what she really thought of Darcy.", audiences: ["book-clubs", "students"] },
  ] as { title: string; line: string; audiences: Audience[] }[],
  tryLabel: "Try this",
  tryHref: "#/signup",
};

/* ---------- testimonials ---------- */

export const testimonials = {
  id: "testimonials",
  title: "What readers say",
  /** Placeholder quotes: each card shows a "Sample" tag while this is true. Replace, then set it to false. */
  sample: true,
  items: [
    {
      quote: "I finally finished a book I'd started three times. Listening on walks, then asking about the parts I'd missed, made it stick.",
      name: "Sample reader",
      role: "Lifelong learner",
    },
    {
      quote: "Revision got so much faster. The quiz questions link straight back to the page, so I never lose the context.",
      name: "Sample student",
      role: "Literature undergraduate",
    },
    {
      quote: "Our book club uses the spoiler guard every month. Nobody gets the ending ruined anymore.",
      name: "Sample organizer",
      role: "Book club host",
    },
  ],
};

/* ---------- FAQ ---------- */

export const faq = {
  id: "faq",
  title: "Questions, answered",
  items: [
    {
      q: "Which file types can I upload?",
      a: "PDF, EPUB, Word (DOCX), plain text and Markdown. Scanned PDFs work too if text recognition (Tesseract) is installed. You can also add free books straight from Project Gutenberg and other public-domain libraries.",
    },
    {
      q: "Who can see my books and conversations?",
      a: "Only you. Every account has its own private library, and BookMind runs on your own computer, so your books, notes and chats stay there. You can export all of it or delete your account at any time.",
    },
    {
      q: "Does it work offline?",
      a: "Yes. With a local AI model (Ollama) and the built-in local voices, everything runs without an internet connection once installed. Cloud AI models are optional.",
    },
    {
      q: "How accurate are the answers?",
      a: "Answers are drawn only from passages of your book, and each claim carries a numbered citation you can open. When the book doesn't cover something, BookMind says so instead of guessing. AI can still make mistakes, so the citations let you check.",
    },
    {
      q: "Which languages does it support?",
      a: "You can upload books in most languages and ask questions in your own. How well it answers depends on the AI model you use. Chapters can be translated side by side into any language. The local voices are English by default, and voices for many other languages can be added.",
    },
    {
      q: "What does it cost?",
      a: "BookMind is free to run on your own computer. If you choose a cloud AI model or cloud voices instead of the local ones, that provider may charge for usage under its own plan.",
    },
  ],
};

/* ---------- closing + footer ---------- */

export const closing = {
  title: "Ready to start the conversation?",
  sub: "Bring a book you love, or one you've been meaning to read.",
  cta: { label: "Get started free", href: "#/signup" },
};

export const footer = {
  tagline: "Talk to any book. Listen to every page.",
  columns: [
    {
      title: "Product",
      links: [
        { label: "Features", href: "#features" },
        { label: "Listening mode", href: "#listen" },
        { label: "How it works", href: "#how-it-works" },
        { label: "Use cases", href: "#use-cases" },
      ],
    },
    {
      title: "Resources",
      links: [
        { label: "FAQ", href: "#faq" },
        { label: "Log in", href: "#/login" },
        { label: "Create an account", href: "#/signup" },
      ],
    },
    {
      title: "Legal",
      links: [
        { label: "Privacy", href: "#/privacy" },
        { label: "Terms", href: "#/terms" },
      ],
    },
  ],
  // Placeholder links: replace "#" with your profiles.
  social: [
    { label: "Source code", icon: "github" as IconName, href: "#" },
    { label: "Email us", icon: "mail" as IconName, href: "#" },
    { label: "News feed", icon: "rss" as IconName, href: "#" },
  ],
  copyright: `© ${new Date().getFullYear()} BookMind`,
};

/* ---------- legal pages (placeholders) ---------- */

export const legal = {
  placeholderNote: "Placeholder text. Replace it with your own policy before publishing.",
  privacy: {
    title: "Privacy",
    updated: "November 2026",
    sections: [
      {
        heading: "What we keep",
        body: "Your account details (email, name, a hash of your password), the books you upload, and what you create with them: chats, notes, highlights, quizzes and settings.",
      },
      { heading: "Where it lives", body: "On the computer or server that runs BookMind. Each account's library is private to that account." },
      {
        heading: "Third parties",
        body: "If you choose a cloud AI model or cloud voices, the text needed for each request is sent to that provider under its own privacy terms.",
      },
      { heading: "Your choices", body: "Download all of your data, or delete your account and everything in it, from Settings at any time." },
    ],
  },
  terms: {
    title: "Terms",
    updated: "November 2026",
    sections: [
      { heading: "Using BookMind", body: "Upload only books you have the right to use. You remain responsible for the content you add." },
      {
        heading: "AI answers",
        body: "Answers are generated from your books and may contain mistakes. Check the cited passages before relying on them.",
      },
      { heading: "Accounts", body: "Keep your password safe. Accounts may be suspended for misuse by whoever runs this BookMind server." },
      { heading: "Changes", body: "These terms may change; the date above shows the latest version." },
    ],
  },
};
