from rag_it1.rag_func import formator_llm
data={
    "messages": [
        {
            "user_id": "U0911MZLHGW",
            "username": "vishwa.fury",
            "text": "i need a frontend dev",
            "app_id": "T091X4YCNAU",
            "channel_id": "C093F2D91JR",
            "session_id": "C093F2D91JR_main"
        },
        {
            "user_id": "U0911MZLHGW",
            "username": "vishwa.fury",
            "text": "i need a backend dev",
            "app_id": "T091X4YCNAU",
            "channel_id": "C093F2D91JR",
            "session_id": "C093F2D91JR_main"
        },
        {
            "user_id": "U0911MZLHGW",
            "username": "vishwa.fury",
            "text": "with 2 years exp for frontend dev",
            "app_id": "T091X4YCNAU",
            "channel_id": "C093F2D91JR",
            "session_id": "C093F2D91JR_main"
        },
        {
            "user_id": "U0911MZLHG89",
            "username": "vishwa.fury",
            "text": "4 yrs exp for backend dev",
            "app_id": "T091X4YCNAU",
            "channel_id": "C093F2D91JR",
            "session_id": "C093F2D91JR_main"
        },
      
    ],
    "batch_size": 5,
    "timestamp": 1751120769.072652
}
formator_llm(data)
