import streamlit as st
import pandas as pd
import re
from datetime import datetime
from googleapiclient.discovery import build
from functools import lru_cache

# Cache decorated function for channel data
@st.cache_data(ttl=3600)
def fetch_channel_data(api_key, channel_id):
    youtube_api = build('youtube', 'v3', developerKey=api_key)
    response = youtube_api.channels().list(part='contentDetails,snippet', id=channel_id).execute()
    return response

# Cache decorated function for playlist items
@st.cache_data(ttl=1800)
def fetch_playlist_items(api_key, playlist_id, page_token=""):
    youtube_api = build('youtube', 'v3', developerKey=api_key)
    return youtube_api.playlistItems().list(
        part='contentDetails',
        playlistId=playlist_id,
        maxResults=50,
        pageToken=page_token
    ).execute()

# Main data fetch
def fetch_youtube_data(api_key, channel_id, start_month_year, end_month_year, keyword, hashtag_keywords, include_description, max_videos):
    try:
        youtube_api = build('youtube', 'v3', developerKey=api_key)

        start_month = int(start_month_year[:2])
        start_year = int(start_month_year[2:])
        end_month = int(end_month_year[:2])
        end_year = int(end_month_year[2:])

        uploads_playlist_response = fetch_channel_data(api_key, channel_id)

        if 'items' not in uploads_playlist_response or len(uploads_playlist_response['items']) == 0:
            st.warning(f"No items found for channel ID: {channel_id}")
            return None

        uploads_playlist_id = uploads_playlist_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        channel_name = uploads_playlist_response['items'][0]['snippet']['title']

        video_data = {
            'Channel Name': [],
            'Video Title': [],
            'Description': []
            'Published Date': [],
            'View Count': []
        }

        next_page_token = ''
        video_count = 0
        while next_page_token is not None and video_count < max_videos:
            playlist_items_response = fetch_playlist_items(api_key, uploads_playlist_id, next_page_token)
            video_ids = []
            video_publish_map = {}

            for item in playlist_items_response['items']:
                vid = item['contentDetails']['videoId']
                published_date = datetime.fromisoformat(item['contentDetails']['videoPublishedAt'][:-1])
                video_publish_map[vid] = published_date

                if start_year <= published_date.year <= end_year and start_month <= published_date.month <= end_month:
                    video_ids.append(vid)

            for video_id in video_ids:
                if video_count >= max_videos:
                    break

                video_response = youtube_api.videos().list(part='statistics,snippet', id=video_id).execute()
                snippet = video_response['items'][0]['snippet']
                statistics = video_response['items'][0]['statistics']

                video_title = snippet.get('title', '')
                view_count = int(statistics.get('viewCount', 0))
                published_date = video_publish_map.get(video_id, datetime.now())

                # Keyword filter
                if keyword:
                    description_preview = snippet.get('description', '')
                    if keyword not in video_title.lower() and keyword not in description_preview.lower():
                        continue

                # Description and hashtag filtering
                if include_description:
                    description = snippet.get('description', '')
                    hashtags = re.findall(r'#\S+', description)
                    hashtags_lower = [h.lower() for h in hashtags]

                    if hashtag_keywords:
                        if not any(h in hashtags_lower for h in hashtag_keywords):
                            continue

                    description_output = ', '.join(hashtags)
                else:
                    description_output = ''

                video_data['Channel Name'].append(channel_name)
                video_data['Video Title'].append(video_title)
                video_data['Description'].append(description_output)
                video_data['Published Date'].append(published_date.date())
                video_data['View Count'].append(view_count)

                video_count += 1

            next_page_token = playlist_items_response.get('nextPageToken')

        return pd.DataFrame(video_data)

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None

# Streamlit UI
st.title("📊 YouTube Channel Hashtag Extractor + Quota Estimator")

api_key = st.text_input("🔑 Enter your YouTube API Key:", type="password")

channel_ids_input = st.text_area("📺 Enter YouTube Channel IDs (one per line):")
channel_ids = [c.strip() for c in channel_ids_input.splitlines() if c.strip()]

with st.expander("❓ How to find a YouTube Channel ID"):
    st.markdown("""
    1. Go to the target channel’s **YouTube page**
    2. Press `Ctrl + U` to **view page source**
    3. Press `Ctrl + F` and search for `channel_id=`
    4. Copy the code after `channel_id=` — it will look like this:  
       `UCxxxxxxxxxxxxxxxxxxxxxx`  
       
    ✅ Example: `UCNpSm55KmljJvQ3Sr20bmTQ`
    """)

col1, col2 = st.columns(2)
with col1:
    start_month_year = st.text_input("Start Month & Year (MMYYYY)", value="012023")
with col2:
    end_month_year = st.text_input("End Month & Year (MMYYYY)", value="062024")

keyword = st.text_input("🔍 Filter by keyword in title or description (optional):").lower()
hashtag_filter = st.text_input("🔎 Filter by hashtag(s), separated by commas (e.g. #Ad, #Marketing)").lower()
include_description = st.checkbox("Include video hashtags)", value=True)

hashtag_keywords = [tag.strip() for tag in hashtag_filter.split(',') if tag.strip()]

max_videos_per_channel = st.slider("🎯 Max videos to fetch per channel", min_value=10, max_value=500, value=100, step=10)

# Quota Estimator
estimated_playlist_cost = (max_videos_per_channel // 50 + 1) * len(channel_ids)
estimated_video_cost = max_videos_per_channel * len(channel_ids)
estimated_channel_cost = len(channel_ids)
total_estimate = estimated_channel_cost + estimated_playlist_cost + estimated_video_cost

st.info(f"Estimated API quota usage: {total_estimate} units")

if st.button("Run Analysis"):
    if not api_key or not channel_ids or not start_month_year or not end_month_year:
        st.warning("Please complete all required fields.")
    else:
        df_list = []
        with st.spinner("Fetching data from YouTube..."):
            for cid in channel_ids:
                df = fetch_youtube_data(api_key, cid, start_month_year, end_month_year, keyword, hashtag_keywords, include_description, max_videos_per_channel)
                if df is not None and not df.empty:
                    df_list.append(df)

        if df_list:
            result_df = pd.concat(df_list, ignore_index=True)
            st.success("✅ Data fetched successfully!")
            st.dataframe(result_df)

            file_name = f"youtube_data_{start_month_year}_{end_month_year}.xlsx"
            result_df.to_excel(file_name, index=False)

            with open(file_name, "rb") as f:
                st.download_button(
                    label="📥 Download Excel File",
                    data=f,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No data found for the selected period.")
