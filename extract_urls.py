import pandas as pd

def extract_urls():
    df_video = pd.read_csv('data/tv_video_analysis_v2.csv')
    df_channel = pd.read_csv('data/tv_channel_ranking_v2.csv')

    print('=== TOP 20 TV VIDEOS WITH URLS ===')
    print()

    top_videos = df_video.nlargest(20, 'viewCount')

    for i, row in top_videos.iterrows():
        video_id = row['videoId']
        title = str(row['title'])[:60]
        channel = str(row['channelTitle'])[:30]
        views = row['viewCount']
        url = f'https://www.youtube.com/watch?v={video_id}'

        print(f'{i+1:2d}. {views:>8,} views')
        print(f'    Channel: {channel}')
        print(f'    Title: {title}')
        print(f'    URL: {url}')
        print()

    print('=' * 80)
    print('=== TOP 15 TV CHANNELS WITH URLS ===')
    print()

    for i, row in df_channel.head(15).iterrows():
        channel_id = row['channelId']
        channel_name = str(row['channelTitle'])
        score = row['final_score']
        subs = row['channelSubscriberCount'] / 1000000
        expert = 'TV Expert' if row['is_tv_expert'] else 'Regular'

        channel_url = f'https://www.youtube.com/channel/{channel_id}'

        print(f'Rank {row["rank"]:2d}: {channel_name}')
        print(f'         Score: {score:.3f} | Subs: {subs:.1f}M | Type: {expert}')
        print(f'         URL: {channel_url}')
        print()

if __name__ == "__main__":
    extract_urls()