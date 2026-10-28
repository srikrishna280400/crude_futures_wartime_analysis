# CRUDE PRICES VOLATALITY ANALYSIS DURING THE IRAN WAR/HORMUZ CRISS OF 2026 

1. The First Principles — Framing the Problem Before Touching Data

The thinking, before any code: future price action is nothing but a repetition of patterns, and AI's real edge isn't chat — it's ingesting massive data, finding patterns, and telling the big-picture data story. So instead of asking a chatbot "will price go up?", the question was reframed: why not train a model on the price data itself, and let it fish for patterns? That single reframe set the entire project's shape — and the basis on which any later model would predict (which ideologies, which data points) was settled deliberately, through clarifying questions, not assumptions.

  The first execution was deliberately primitive — a minimum viable approach to test whether the pattern premise held at all:
	  Day-type buckets from price movement alone: 
		(i) full-day rallies, 
		(ii) full-day dips, 
		(iii) two-sided violent whipsaw, 
		(iv) flat days that still ended at the day's high/low.
		
   News overlay — each bucket tagged escalation / de-escalation / neutral. This surfaced the project's founding observation: price repeatedly failed to reflect breakout news — the first hard evidence of manipulation, and the reason "trust the tape, quantify the divergence" became a design principle.
	
   Session windows — buckets split across Asian / European / US market hours, on the reasoning that countries with different Hormuz exposure (Japan, Europe, India, US) move crude differently at their own market opens.
   
   The output structure: a two-tiered matrix — day-types × session windows × three news flags — built purely on WTI/Brent open-close prices via ChatGPT/Claude web search, over a short timeframe.
	
   Crucially, even this primitive stage was designed backwards from the questions the eventual model must answer — the dataset was structured so a later model could answer: 
		i) what past day is today most similar to? 
		ii) Which session windows drive the day, in which direction, on what news type? 
		iii) When the normal pattern fails, what alternate repeatable pattern takes over? 
		iv) If pattern P occurred on day-type X in window Y, what Q preceded and what R succeeded it? How far does price travel in INR/MCX ticks on this kind of day? Which windows are safest for entry, and which are stop-hunt traps? 
		v) Do manipulative bearish moves follow a signature pattern by time-of-day and news flag?
