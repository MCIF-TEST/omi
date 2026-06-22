# Schema Comparison

How the discovered datasets differ, grouped by detected family, and how each maps into the unified Omi schema (see `UNIFIED_OMI_SCHEMA.md`).

| family | domain | grain | files | example columns | unified mapping |
|---|---|---|---|---|---|
| ai_text_2026 | ai_text | text | 1 | text_id, label, source_model, domain, text_content, topic_hint | text_content→text, label→authenticity_label |
| ai_text_v1 | ai_text | text | 1 | id, text, human_or_ai, source_model, prompt, domain | text→text, human_or_ai→authenticity_label, language→lang |
| bot_detection | bot | account | 1 | User ID, Username, Tweet, Retweet Count, Mention Count, Follower Count | quarantine poison — not merged |
| bot_tsv | bot | account | 2 | id, label | id→author_id, tsv label word→label |
| cresci_json | bot | tweet | 1 | created_at, user | user.id→author_id, text→text, join cresci tsv→label |
| fsm_profile | authenticity | account | 2 | platform, has_profile_pic, bio_length, username_randomness, followers, following | username→author_id, numeric cols→numeric, is_fake→label |
| generic_account | authenticity | account | 2 | Twitter_User_Name, Following, Followers, Verified, Link, Location | numeric→numeric (archive; not merged) |
| io_tweets | coordination | tweet | 42 | tweetid, userid, user_display_name, user_screen_name, user_reported_location, user_profile_description | userid→author_id, tweet_text→text, tweet_time→created_at, label=1 (io) |
| io_users | coordination | account | 10 | userid, user_display_name, user_screen_name, user_reported_location, user_profile_description, user_profile_url | userid→author_id, follower/following→numeric, label=1 (io) |
| reddit_comment | bot | comment | 1 | comment_id, subreddit, account_age_days, user_karma, reply_delay_seconds, sentiment_score | comment_id→author_id, numeric→numeric, is_bot_flag→label |
| reference | reference | account | 1 | user_id, age, count, activity, bot_score_english | numeric (bot_score)→numeric, label=None |
| twitterdata | authenticity | tweet | 3 | Twitter_User_Name, Twitter_Account, Twitter_User_Description, Tweet_id, Tweet_created_at, Tweet_text | Tweet_text→text, Twitter_Account→author_id, Label(1=human)→inverted label |
| unknown | other | unknown | 2 | userid, userDisplayName, userScreenName, userReportedLocation, userProfileDescription, userProfileUrl | no converter |
| userdump | authenticity | account | 2 | id, name, screen_name, statuses_count, followers_count, friends_count | screen_name→author_id, numeric→numeric, filename→label |
| xlsx | authenticity | account | 1 | platform, has_profile_pic, bio_length, username_randomness, followers, following | - |

### Key differences
- **Grain varies**: account (profiles), tweet (IO / TwitterData / cresci), comment (reddit), text (AI sets). The unified schema keeps a `grain` column so these never silently merge into one training population.
- **Label encoding varies**: `is_fake`, `human_or_ai`, headerless TSV words, filename, inverted `Label` (1=human), implicit io_disclosure (=1), or none (reference). All normalize to `authenticity_label` ∈ {0,1,null} + `label_raw`.
- **Features vary**: account sets carry numeric profile features (→ `numeric_features_json`); tweet/text sets carry `text`. No dataset carries engine detector outputs.
