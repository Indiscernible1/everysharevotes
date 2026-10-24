export type Broker = {
  name: string;
  inTeslaGuide: boolean;
  steps: string[];
};

const guideAsOf = "Instructions below are copied from Tesla’s vote guide as retrieved on October 24, 2026.";

export const voteGuide = {
  href: "https://ir.tesla.com/shareholders/vote",
  asOf: "October 24, 2026",
  recordDateLanguage: "The page says a holder must have held shares as of the September 15 record date. It does not state the year of that record date on the page.",
  emailYear: "The page tells holders to search for emails received in 2025.",
  phoneUs: "(877) 717-3936",
  phoneIntl: "+1 (412) 232-3651",
  solicitor: "Innisfree M&A Incorporated",
  note: guideAsOf,
};

export const brokers: Broker[] = [
  {
    name: "Fidelity",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says the message may come from Fidelity.Investments.email@shareholderdocs.fidelity.com, e-notification@edocs.mybrokerageinfo.com, or id@proxyvote.com, and to search the keyword Tesla.",
      "Open the email and follow the instructions in it.",
    ],
  },
  {
    name: "Robinhood",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says to search: noreply@robinhood.com Tesla.",
      "Open the email and click VOTE.",
    ],
  },
  {
    name: "Interactive Brokers",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says to search: interactivebrokers@proxydocs.com Tesla.",
      "Open the email and follow the instructions in it.",
    ],
  },
  {
    name: "Charles Schwab, including former TD Ameritrade accounts",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025 using: id@proxyvote.com Tesla.",
      "Tesla’s guide also says you can log into the brokerage account, search for proxy events, and open proxy events.",
      "Or use a 16-digit control number from postal mail at www.proxyvote.com.",
      "Tesla’s guide also says mail, phone, or a QR code may be offered, and to contact the broker if no instructions arrived.",
    ],
  },
  {
    name: "Merrill",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says to search id@proxyvote.com Tesla, and also to search the inbox for Tesla because the message may come from another address.",
      "Open the email and follow the instructions in it.",
    ],
  },
  {
    name: "Vanguard Brokerage Services",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says to search: id@proxyvote.com Tesla.",
      "Open the email and follow the instructions in it.",
    ],
  },
  {
    name: "Morgan Stanley, including former E*TRADE accounts",
    inTeslaGuide: true,
    steps: [
      "Search the inbox tied to the brokerage account, including spam, for an email received in 2025.",
      "Tesla’s guide says to search: id@proxyvote.com Tesla.",
      "Open the email and follow the instructions in it.",
    ],
  },
  {
    name: "Webull",
    inTeslaGuide: false,
    steps: [
      "Tesla’s vote guide, as retrieved on October 24, 2026, has no Webull section.",
      "The same page’s “all other brokers” instructions say to search 2025 email for id@proxyvote.com Tesla, @proxydocs.com Tesla, and @saytechnologies.com Tesla, then follow the message if one is there.",
      "If nothing arrives, contact Webull and ask whether the account can submit proxy instructions.",
    ],
  },
];

export const otherBrokers = [
  "Search 2025 email for id@proxyvote.com Tesla.",
  "Search for @proxydocs.com Tesla.",
  "Search for @saytechnologies.com Tesla.",
  "If a message is there, open it and follow it. Tesla’s guide says some brokers outside the United States do not provide retail proxy voting, and to ask the broker if no instructions arrive.",
];
