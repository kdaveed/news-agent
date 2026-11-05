
@agent - this will be the most conscise at the end
at most 2-3 page long extract of how did I approach
the problem.




- Let the agent explore opportunities
- Two most prospective - Wikipedia Event based on the -  GDELT

- Go for the GDELT data processing problem
  - Figure out what are the challenges
- Check if we can parallize the expiremntation



# Codex Starting another agent - Codex

- Originally I wanted ask Codex about the GDELT data processing
  approach, then I relized. 


- Let it start from the beginning and lets see how it
  thinks and what it finds.


- Seems that Codex found the same way GDELT as the best

- But when I was about to reason that GDELT is the choice,
  I realized it worth a try to go for the feeds, because 
  they can easily be used and the uncertainty that was
  clear by the GDELP + Wikipedia approach identified by
  the Claude thread can be mitigated with the RSS feeds.




# Claude Thread 

- As Claude was working on the three GDELT data comparison, who will I verify 
  which was the right one. How much I rely on its judgement. 

- The idea is to establish some initial metrics system for the approaches

- Outcome is a pretty long thread with lot of information. Really hard to read. 
  --> So i need to ask them for a summary and some benchmar.

- I want to ask the agent to provide me a table with different it can precisely 
  identify regarding the different approaches.


- As the Codex thread was able to find reliable feeds I told him to write it down
  and I am going to ask Claude to summarize what we know and consider the RSS 
  feeds as well and suggest the architecture of the first version.


- @agent - Combining sources only reduces uncertainty if their errors are independent.
  This is an important take for me. 

  It's slow. Entries are written hours to a day later, and 4 Nov still had only 6. A real-time alert can't wait for it.

  Okay -> this is a really important note which comes up for the first time
  
   

@agent

- Approach comparison
- Takeaways 


@thought

- After the evaluation the whole approach looked way more complicated 
  and fragile then it was initially suggested by the agent. 


@me

So you mentioned that each appraoch has failed in different ways, so each
of them had a flaw. My question, based on the finding can you think of
a solution that can beat each of the three.

- Asking for summarizing again what was the task with the initial data and how
  exactly the three approaches was doing. Refresher. Putting the problem/solution
  into a new fresh context. 

@turn



# Wikepedia Events

- It seems to be pretty well referenced and a condesed way, that is even 
  human readable
- Task - verify with both with Codex and Claude - how accurate and relevant Wikipedia is
  the result will have an effect on the next question

  Note at this point: I might need to think a bit on my own - what  

- The big deision related to Wikipedia - is it source which we validate with the GDELT data,
  or we validate the GDELT data with Wikipedia
  or they are rather have identical relevance.





# Takeaways


- Its good to have multiple resource 
- When for instance one agent arrives to a paralell comparative step - so it is
  working - the other agent can be started


- Before comparison - important to give an agent the instruction that should return
  and easy to read table with specific comparisons.


- Other takeaway from the Codex research - when I ask for opportunities concreate things
  should be returned. Not some vague stuff like RSS/feed. Concrete feeds, with relevant info. 
 