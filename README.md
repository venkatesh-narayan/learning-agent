# learning-agent

## Introduction
This project is essentially my own implementation of Perplexity Pro, but tuned with a bit more personalization to help users learn.

Motivation: I often search things up on Perplexity when trying to learn something new, and after a few weeks of searching, I come across an article / blog post / paper that is super useful (for example, because it explains something really well, or just completely changes the way I think about the space) - and I always think, "it would've been so nice if I found this a few weeks earlier." This project aims at solving that.  

This project has two features:

1. Personalized recommandation engine: given everything a user has searched for, what links should be surfaced that still answer their question but also help lead them better towards their goal?

2. Personalized query suggestions: given everything a user has searched for, what are some interesting questions that the user can ask?

As of right now, this is just an MVP - there are still some parts that could be tuned to perform better. See [Future Directions](#future-directions) below.

# Recommendation Engine Flow

This is what the flow looks like:

<img width="1468" alt="image" src="https://github.com/user-attachments/assets/dd6f2c94-1687-4d4b-a2cd-70378680b08d" />

1. Separate queries into "query lines" - for example, if the user chats a lot about EV companies and then decides to switch the topic to digital analytics companies, the recommendation engine should only focus on the "digital analytics companies" topic, because the "EV companies" topic is unrelated to the current focus. By separating queries into different query lines, we can control what information gets sent to the LLM when trying to generate recommendations.

2. Then, from the current query line, we get the base Perplexity response (each query line contains all queries and all responses for each of those queries). This is used to get a sense of what topics the user has been exposed to / what they might be comfortable with. We also find any other related query lines, and track the user's current knowledge state in this general field. For example, if the user explored a lot about NVIDIA and then switched the topic to chips in EV's, we should use the knowledge that the user gained from that NVIDIA conversation here as well; we shouldn't assume they're a beginner in this field.

3. Also from the current query line, we find what the user's goals are. This is super important: we want to make sure the surfaced content aligns deeply with the user's goal.

4. Then, using (2) and (3), we detect what type of "learning moment" the query line falls under. In particular, there are four different learning moments that I've focused on:
    - `new_topic_no_context`: completely new topic, and the user has no background
    - `new_topic_with_context`: new topic, but the user has background in relevant fields
    - `concept_struggle`: the user is struggling to understand a certain concept
    - `goal_direction` the user is searching with too much breadth and not enough depth

5. Then, using (2), (3), and (4), we generate appropriate search queries for the user, with different criteria for different learning moments. For example, if it's a new topic, we'd like to generate some "forward-thinking" queries; if it's a concept struggle, we just want to find links that give intuitive explanations to address your concerns; if it's a goal direction, we'd like to double down on a certain path that we think would be the most useful for you and provide some structure to move forward.

6. Then, for each search query from (5), we get the corresponding Perplexity citations. For each citation, we scrape that link and extract additional (financial) metadata from it.

7. Using (2), (3), (4), and (6), we figure out whether or not each citation is actually relevant to the user. If nothing is found, we generate a reason for why our search attempts failed, and go back to (5), which will utilize this information to come up with a new set of search queries.


## Future Directions
I do think that in the limit, this can be seen as "100 versions of you that surf the web and find content that's super relevant for you exactly when you need it (or even before that)". If a user has done enough searches, I totally think we could use the concepts from [this paper](https://arxiv.org/pdf/2304.03442) to make this kind of thing.

In terms of general quality improvements that can be made:

1. As of right now, the search queries that are generated are reasonable - they certainly go in the right direction and some of them are generally interesting directions, but I do feel that they can improve. It's not super straightforward though, because we don't want to get so creative that we stray away from the actual goal and show irrelevant content, but we don't want to be so lackluster that search quality doesn't improve above the baseline. Adding more curated examples to the `generate_strategies` system prompt can definitely help (for example, `goal_direction` doesn't work super well right now). We're also searching with `depth = 1`; we could search with `depth > 1` - that is, have GPT come up with a set of query lines, rather than a set of individual queries.

2. The content filterer can definitely improve. I think it's too permissive, and lets in content that's only kind of relevant. Also, I end up seeing a good amount of links that are only high-level useful - that is, the generated explanation for the recommendation sounds great, but when I open the link, there isn't really that much information on the page. I think this is partly due to the `FinancialContentExtractor` not maintaining a sense of "depth" or "utility" of the actual site. It just looks at the content and tries to split it into different `ContentSection`'s, each of which only contain the high level ideas mentioned in the actual section of the page. I think it we tracked things like how well the website explains the information on the page, we could use that to improve the quality of the recommendations. On top of this, general improvements can also be made to the `evaluate_content` system prompt (for example, adding more hand curated examples for preferred behavior). But the filterer can only do so much - if the `ContentDiscovery` module just returns a pile of high-level links, the filterer can't do anything to fix that. So the previous point on search query improvements is still very relevant here.

3. I also think there's a lot more information that I could track regarding the interactions between the user and the recommended content. For example, what pages people have clicked on, how long people spend reading the page, what text the users highlight, etc. There is some backend infrastructure for this, but my frontend currently isn't hooked up to track all of that information. Also, even if the frontend were set up to I'm not particularly convinced that the existing implementation will do a good job at surfacing content that really follows the patterns from that interaction data. The interaction data is basically just stuffed into the user prompts at a bunch of different points in the overall flow, and it's difficult to say how much the LLM will actually use this info to make the necessary judgments. But it could definitely play more of a foreward role if we go more towards a TikTok-esque approach of having content embeddings and dynamically generated user embeddings that have the property that if the dot product between user embedding and content embedding is high, the content is a good fit for the user.
