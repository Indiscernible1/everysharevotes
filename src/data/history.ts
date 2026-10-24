export type FoundCell = {
  status: "found";
  label: string;
  detail: string;
  href: string;
  source: string;
  asOf: string;
};

export type HistoryCell = FoundCell | { status: "not-found" };

export type Meeting = {
  id: string;
  name: string;
  date: string;
};

export const meetings: Meeting[] = [
  { id: "solarcity", name: "SolarCity acquisition", date: "2016-11-17" },
  { id: "pay2018", name: "2018 CEO performance award", date: "2018-03-21" },
  { id: "directors2024", name: "2024 director elections", date: "2024-06-13" },
  { id: "ratify2024", name: "2024 ratification of the 2018 award", date: "2024-06-13" },
  { id: "texas2024", name: "2024 move to Texas", date: "2024-06-13" },
  { id: "directors2025", name: "2025 director elections", date: "2025-11-06" },
  { id: "pay2025", name: "2025 CEO performance award", date: "2025-11-06" },
  { id: "xai2025", name: "2025 xAI investment proposal", date: "2025-11-06" },
  { id: "supermajority2025", name: "2025 supermajority elimination", date: "2025-11-06" },
];

const notFound: HistoryCell = { status: "not-found" };

const reutersSolar =
  "https://www.reuters.com/article/business/tesla-motors-solarcity-deal-gets-a-boost-from-shareholder-advisory-firm-idUSKBN12Z1Y5/";
const ap2018 = "https://apnews.com/general-news-db495cdf8ee14f7fb18c6fc8a2d7e08d";
const reutersIss2024 =
  "https://www.reuters.com/business/autos-transportation/iss-recommends-votes-against-2018-pay-plan-tesla-ceo-elon-musk-2024-05-31/";
const reutersGl2024 =
  "https://www.reuters.com/business/autos-transportation/tesla-shareholders-advised-reject-musks-56-bln-pay-2024-05-25/";
const cnbcIss2024 = "https://www.cnbc.com/2024/05/31/elon-musk-tesla-tsla-pay-package-shareholders.html";
const biGlTexas =
  "https://www.businessinsider.com/tesla-investors-advised-vote-against-elon-musk-pay-package-2024-5";
const teslaGlLetter =
  "https://www.sec.gov/Archives/edgar/data/1318605/000110465924066122/tm2413800d12_defa14a.htm";
const reuters2025 =
  "https://www.reuters.com/sustainability/boards-policy-regulation/proxy-firm-glass-lewis-joins-iss-urging-vote-against-musks-1-trillion-pay-2025-10-20/";
const cnbcIss2025 =
  "https://www.cnbc.com/2025/10/17/proxy-advisor-iss-opposes-tesla-ceo-elon-musk-1-trillion-pay-plan.html";
const teslaAdvisorLetter =
  "https://www.sec.gov/Archives/edgar/data/1318605/000110465925101278/tm252289d39_defa14a.htm";

export const recommendationRows: {
  name: string;
  note: string;
  cells: Record<string, HistoryCell>;
}[] = [
  {
    name: "ISS recommendation",
    note: "A proxy-adviser recommendation. It is not a count of shares voted.",
    cells: {
      solarcity: {
        status: "found",
        label: "For",
        detail: "Reuters reported that ISS recommended investors approve the acquisition.",
        href: reutersSolar,
        source: "Reuters",
        asOf: "Ahead of the November 17, 2016 meeting",
      },
      pay2018: {
        status: "found",
        label: "Against",
        detail: "The Associated Press reported that ISS recommended a vote against the pay plan.",
        href: ap2018,
        source: "Associated Press",
        asOf: "Ahead of the March 21, 2018 meeting",
      },
      ratify2024: {
        status: "found",
        label: "Against",
        detail: "Reuters reported that ISS recommended voting against ratifying the 2018 pay plan.",
        href: reutersIss2024,
        source: "Reuters",
        asOf: "May 31, 2024",
      },
      texas2024: {
        status: "found",
        label: "For",
        detail:
          "Reuters reported that ISS backed the move from Delaware to Texas. CNBC, describing the ISS report, called that support cautionary.",
        href: reutersIss2024,
        source: "Reuters; CNBC on the cautionary wording",
        asOf: "May 31, 2024",
      },
      pay2025: {
        status: "found",
        label: "Against",
        detail: "Reuters reported that ISS urged investors to reject the 2025 pay package.",
        href: reuters2025,
        source: "Reuters",
        asOf: "October 20, 2025",
      },
      directors2025: {
        status: "found",
        label: "Against Ira Ehrenpreis",
        detail:
          "CNBC reported that ISS recommended against reinstating director Ira Ehrenpreis. That article does not state ISS’s recommendation on Joe Gebbia or Kathleen Wilson-Thompson.",
        href: cnbcIss2025,
        source: "CNBC",
        asOf: "October 17, 2025",
      },
      xai2025: {
        status: "found",
        label: "Against",
        detail:
          "CNBC reported that ISS recommended voting against giving the board authorization to invest in xAI.",
        href: cnbcIss2025,
        source: "CNBC",
        asOf: "October 17, 2025",
      },
    },
  },
  {
    name: "Glass Lewis recommendation",
    note: "A proxy-adviser recommendation. It is not a count of shares voted.",
    cells: {
      solarcity: notFound,
      pay2018: {
        status: "found",
        label: "Against",
        detail: "The Associated Press reported that Glass Lewis recommended a vote against the pay plan.",
        href: ap2018,
        source: "Associated Press",
        asOf: "Ahead of the March 21, 2018 meeting",
      },
      ratify2024: {
        status: "found",
        label: "Against",
        detail: "Reuters reported that Glass Lewis urged shareholders to reject the pay package.",
        href: reutersGl2024,
        source: "Reuters",
        asOf: "May 25, 2024",
      },
      texas2024: {
        status: "found",
        label: "Against",
        detail:
          "Business Insider reported that Glass Lewis urged a vote against the Texas reincorporation. Tesla’s May 29, 2024 stockholder letter responds to Glass Lewis on that proposal.",
        href: biGlTexas,
        source: "Business Insider; Tesla DEFA14A",
        asOf: "May 2024",
      },
      pay2025: {
        status: "found",
        label: "Against",
        detail: "Reuters reported that Glass Lewis recommended voting against the 2025 pay package.",
        href: reuters2025,
        source: "Reuters",
        asOf: "October 20, 2025",
      },
      directors2025: {
        status: "found",
        label: "Against Ira and Kathleen",
        detail:
          "Tesla’s shareholder letter filed as additional proxy material says Glass Lewis recommended against Ira Ehrenpreis and Kathleen Wilson-Thompson. The letter does not, in that passage, state a Glass Lewis line on Joe Gebbia.",
        href: teslaAdvisorLetter,
        source: "Tesla DEFA14A",
        asOf: "October 21, 2025",
      },
    },
  },
];

export const extraSources = {
  cnbcIss2024,
  teslaGlLetter,
  cnbcIss2025,
  teslaAdvisorLetter,
};

export const outcomes = [
  {
    id: "solarcity",
    name: "SolarCity acquisition",
    meeting: "November 17, 2016",
    result: "Approved",
    counts:
      "Including affiliated shares: 100,537,323 for; 12,067,314 against; 569,421 abstentions; 0 broker non-votes. Excluding the Excluded Tesla Parties: 68,788,787 for; 12,067,314 against; 569,421 abstentions. The 8-K says the excluding-affiliates votes in favor were approximately 85.1% of votes cast.",
    note: "Counts are as certified in the 8-K and are not adjusted for later stock splits.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000119312516772291/d297885d8k.htm",
    source: "Tesla 8-K filed November 18, 2016",
  },
  {
    id: "pay2018",
    name: "2018 CEO performance award",
    meeting: "March 21, 2018",
    result: "Approved",
    counts:
      "NASDAQ standard: 96,795,092 for; 23,407,632 against; 0 broker non-votes (about 81% of votes cast, as stated in the 8-K). Bylaws standard adds 173,167 abstentions (about 80% of shares present and entitled to vote). Disinterested standard, excluding Elon Musk and Kimbal Musk: 63,014,339 for; 23,407,632 against (about 73% of those votes cast).",
    note: "Counts are as certified in the 8-K and are not adjusted for later stock splits.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000156459018006479/tsla-8k_20180321.htm",
    source: "Tesla 8-K for the March 21, 2018 special meeting",
  },
  {
    id: "ratify2024",
    name: "2024 ratification of the 2018 award",
    meeting: "June 13, 2024",
    result: "Approved",
    counts:
      "Under the NASDAQ standard reported in the 8-K: 1,760,780,650 for; 528,908,419 against; 335,111,943 broker non-votes. The 8-K says votes in favor were approximately 77% of votes cast under that standard. The same 8-K also reports a bylaws standard and a disinterested standard.",
    note: "Abstentions under the other standards are in the 8-K. This cell does not restate numbers that were not copied here.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465924071439/tm2413800d31_8k.htm",
    source: "Tesla 8-K filed June 14, 2024",
  },
  {
    id: "texas2024",
    name: "2024 conversion from Delaware to Texas",
    meeting: "June 13, 2024",
    result: "Approved",
    counts:
      "2,000,873,803 for; 293,910,071 against; 15,485,016 abstentions; 335,111,943 broker non-votes. The 8-K says the votes in favor were approximately 63% of outstanding shares entitled to vote. A separate disinterested standard is also reported in the 8-K.",
    note: "Meeting date June 13, 2024. Filing date June 14, 2024.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465924071439/tm2413800d31_8k.htm",
    source: "Tesla 8-K filed June 14, 2024",
  },
  {
    id: "pay2025",
    name: "2025 CEO performance award",
    meeting: "November 6, 2025",
    result: "Approved",
    counts:
      "1,892,235,822 for; 564,940,908 against; 12,227,846 abstained; 302,456,274 broker non-votes.",
    note: "The 8-K says the proposal was approved. This page does not calculate a percentage from those counts.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465925108507/0001104659-25-108507.txt",
    source: "Tesla 8-K reporting the November 6, 2025 annual meeting",
  },
  {
    id: "xai2025",
    name: "2025 xAI investment proposal",
    meeting: "November 6, 2025",
    result: "Not approved",
    counts:
      "1,058,999,435 for; 916,321,296 against; 473,073,200 abstained; 302,456,274 broker non-votes.",
    note: "The 8-K says more votes were cast for than against, and the proposal was not approved because the bylaws generally treat abstentions as votes against.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465925108507/0001104659-25-108507.txt",
    source: "Tesla 8-K reporting the November 6, 2025 annual meeting",
  },
  {
    id: "supermajority2025",
    name: "2025 supermajority elimination",
    meeting: "November 6, 2025",
    result: "Not approved",
    counts:
      "1,309,549,644 for; 955,682,310 against; 181,764,443 abstained; 302,456,274 broker non-votes.",
    note: "Management proposal to eliminate applicable supermajority voting requirements. This page does not calculate a percentage from those counts.",
    href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465925108507/0001104659-25-108507.txt",
    source: "Tesla 8-K reporting the November 6, 2025 annual meeting",
  },
];

export const xai = {
  meeting: "November 6, 2025",
  counts: "1,058,999,435 for; 916,321,296 against; 473,073,200 abstained; 302,456,274 broker non-votes.",
  prose:
    "Proposal 7 was a shareholder proposal on board authorization of an investment in x.AI Corp. The 8-K says more votes were cast in favor than against, but the proposal was not approved because the bylaws generally treat abstentions as votes against.",
  href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465925108507/0001104659-25-108507.txt",
  source: "Tesla 8-K reporting the November 6, 2025 annual meeting",
};

export const supermajority2025 = {
  counts: "1,309,549,644 for; 955,682,310 against; 181,764,443 abstained; 302,456,274 broker non-votes.",
  prose:
    "A management proposal to eliminate applicable supermajority voting requirements in the certificate of formation and bylaws was not approved.",
  href: "https://www.sec.gov/Archives/edgar/data/1318605/000110465925108507/0001104659-25-108507.txt",
  source: "Tesla 8-K reporting the November 6, 2025 annual meeting",
};
