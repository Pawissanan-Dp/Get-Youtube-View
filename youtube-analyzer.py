import streamlit as st
import pandas as pd
import re
from datetime import datetime
from googleapiclient.discovery import build

# ----------------------------
# Existing functions
# ----------------------------
@st.cache_data(ttl=3600)
def fetch_channel_data(api_key, channel_id):
    youtube_api = build('youtube', 'v3', developerKey=api_key)
    response = youtube_api.channels().list(part='contentDetails,snippet', id=channel_id).execute()
    return response

@st.cache_data(ttl=1800)
def fetch_playlist_items(api_key, playlist_id, page_token=""):
    youtube_api = build('youtube', 'v3', developerKey=api_key)
    return youtube_api.playlistItems().list(
        part='contentDetails',
        playlistId=playlist_id,
        maxResults=50,
        pageToken=page_token
    ).execute()

# ----------------------------
# NEW FUNCTION: Search by Hashtag
# ----------------------------
@st.cache_data(ttl=1800)
def fetch_videos_by_hashtag(api_key, hashtag, start_month_year, end_month_year):
    youtube_api = build("youtube", "v3", developerKey=api_key)

    start_date = datetime.strptime(start_month_year, "%m%Y")
    end_date = datetime.strptime(end_month_year, "%m%Y").replace(day=28)

    video_data = {
        "Channel Name": [],
        "Video Title": [],
        "Description": [],
        "Published Date": [],
        "View Count": []
    }

    next_page_token = None
    while True:
        search_response = youtube_api.search().list(
            q=hashtag,
            type="video",
            part="id,snippet",
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        video_ids = []
        publish_map = {}

        for item in search_response.get("items", []):
            # Some results might not be videos (e.g., missing videoId)
                vid = item.get("id", {}).get("videoId")
                if not vid:
                    continue

                published_date = datetime.fromisoformat(item["snippet"]["publishedAt"][:-1])

                if start_date <= published_date <= end_date:
                    video_ids.append(vid)
                    publish_map[vid] = published_date

        if video_ids:
            for i in range(0, len(video_ids), 50):
                batch_ids = video_ids[i:i+50]
                video_response = youtube_api.videos().list(
                    part="statistics,snippet",
                    id=",".join(batch_ids)
                ).execute()

                for video in video_response.get("items", []):
                    snippet = video["snippet"]
                    statistics = video["statistics"]

                    video_data["Channel Name"].append(snippet.get("channelTitle", ""))
                    video_data["Video Title"].append(snippet.get("title", ""))
                    video_data["Description"].append(snippet.get("description", ""))
                    video_data["Published Date"].append(publish_map.get(video["id"], datetime.now()).date())
                    video_data["View Count"].append(int(statistics.get("viewCount", 0)))

        next_page_token = search_response.get("nextPageToken")
        if not next_page_token:
            break

    return pd.DataFrame(video_data)

# ----------------------------
# Your existing fetch_youtube_data function stays as-is
# ----------------------------
def fetch_youtube_data(api_key, channel_id, start_month_year, end_month_year, keyword, hashtag_keywords):
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
            'Description': [],
            'Published Date': [],
            'View Count': []
        }

        next_page_token = ''
        while next_page_token is not None:
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
                description = snippet.get('description', '')
                hashtags = re.findall(r'#\S+', description)
                hashtags_lower = [h.lower() for h in hashtags]

                if hashtag_keywords:
                    if not any(h in hashtags_lower for h in hashtag_keywords):
                        continue

                description_output = ', '.join(hashtags)

                video_data['Channel Name'].append(channel_name)
                video_data['Video Title'].append(video_title)
                video_data['Description'].append(description_output)
                video_data['Published Date'].append(published_date.date())
                video_data['View Count'].append(view_count)

            next_page_token = playlist_items_response.get('nextPageToken')

        return pd.DataFrame(video_data)

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        return None

# ----------------------------
# Streamlit UI
# ----------------------------
st.title("YouTube Channel View Extractor")
st.markdown("""Report bug: Pawissanan.Denphatcharangkul@initiative.com""")

api_key = st.text_input("🔑 Enter your YouTube API Key:", type="password")

# NEW: add a radio button to pick search mode
search_mode = st.radio("Choose Search Mode:", ["Channel Uploads", "Hashtag Search"])

if search_mode == "Channel Uploads":
    channel_ids_input = st.text_area("📺 Enter YouTube Channel IDs (one per line):")
    channel_ids = [c.strip() for c in channel_ids_input.splitlines() if c.strip()]

    with st.expander("❓ How to find a YouTube Channel ID"):
        st.markdown("""(instructions stay the same)""")

elif search_mode == "Hashtag Search":
    hashtag_input = st.text_input("Enter hashtag (e.g. #AI)").strip()

# Shared date range (applies to both modes)
col1, col2 = st.columns(2)
with col1:
    start_month_year = st.text_input("Start Month & Year (MMYYYY)")
with col2:
    end_month_year = st.text_input("End Month & Year (MMYYYY)")

# Filters ONLY for Channel Uploads
if search_mode == "Channel Uploads":
    keyword = st.text_input("🔍 Filter by keyword in title or description (optional):").lower()
    hashtag_filter = st.text_input("🔎 Filter by hashtag(s), separated by commas (e.g. #AI, #tech)").lower()
    hashtag_keywords = [tag.strip() for tag in hashtag_filter.split(',') if tag.strip()]
else:
    keyword = ""
    hashtag_keywords = []

    # --- NEW: Warning for large date range ---
    if start_month_year and end_month_year:
        try:
            start_date = datetime.strptime(start_month_year, "%m%Y")
            end_date = datetime.strptime(end_month_year, "%m%Y")
            # calculate difference in months
            month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            if month_diff > 1:
                st.warning("⚠️ Date range is more than 2 month. Quota might reach the limit if there are more than 500 videos.")
        except ValueError:
            st.warning("⚠️ Invalid date format. Please use MMYYYY.")

# ----------------------------
# Run button
# ----------------------------
if st.button("Run Analysis"):
    if not api_key or not start_month_year or not end_month_year:
        st.warning("Please complete all required fields.")
    else:
        df_list = []
        with st.spinner("Fetching data from YouTube..."):

            if search_mode == "Channel Uploads":
                if not channel_ids:
                    st.warning("Please enter at least one channel ID.")
                else:
                    for cid in channel_ids:
                        df = fetch_youtube_data(api_key, cid, start_month_year, end_month_year, keyword, hashtag_keywords)
                        if df is not None and not df.empty:
                            df_list.append(df)

            elif search_mode == "Hashtag Search":
                if not hashtag_input:
                    st.warning("Please enter a hashtag.")
                else:
                    df = fetch_videos_by_hashtag(api_key, hashtag_input, start_month_year, end_month_year)
                    if df is not None and not df.empty:
                        df_list.append(df)

        # Combine and show results
        if df_list:
            result_df = pd.concat(df_list, ignore_index=True)
            st.success("✅ Data fetched successfully!")
            st.dataframe(result_df)

            file_name = f"youtube_data_{start_month_year}_{end_month_year}.xlsx"
            import io
            output = io.BytesIO()
            result_df.to_excel(output, index=False, engine="openpyxl")

            st.download_button(
                label="📥 Download Excel File",
                data=output.getvalue(),
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No data found for the selected period.")
