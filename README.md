This is data collection pipeline for a research study to investigate the relationship between the production of incivility and political ideology on Bluesky. The pipeline has four main parts:

1. Label Listener : Listens to the Bluesky Labels firehose and collects label data on 'rude' and various 'intolerant' labels
2. Post Listener : Listens to the Bluesky Repos firehose and collects DIDs of users who have created a post
3. DID extractor : Extracts the DID information from the label and post data and save them to two different files
4. Profile extractor : Reads the DIDs, and visits the user profile to extract relevant profile information and feed information

All these are run through separate threads in the main file.
