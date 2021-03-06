import json
import redis
import greenstalk
import uuid

from cassandra.cqlengine import connection
from cassandra.query import SimpleStatement
from cassandra.cluster import Cluster
from cassandra.query import dict_factory

def setup_cassandra_connection():
    connection.setup(['127.0.0.1'], "default_keyspace", protocol_version=3)
    

def unregister_cassandra_connection():
    connection.unregister_connection('default_cas')

def get_cassandra_session():
    cluster = Cluster(protocol_version=3)
    session = cluster.connect()
    session.set_keyspace("default_keyspace")
    session.row_factory = dict_factory
    return session

cassandra_session = get_cassandra_session()

r = redis.Redis(host='localhost', port=6379, db=0)

timeline_genre_combo = 'Action,Comedy,Drama'

# set the lookup table status to 'processing' =======
#read from main db and add to cassandra with partition key = timeline_genre_combo and add a corresponding sorted list to redis
#update timeline lookup table to ready, add entries to genre to timeline mappings


#NEEDS A STATIC LIST OF MOVIE + GENRE TO BUILD TIMELINE..? Edit:No , the timelines get synchronised when someone upvotes a movie 
count = 0 

def get_movies_from_db_build_timeline(db_session,timeline_genre_combo):
    print('Starting to build timeline for: ',timeline_genre_combo)
    genre_filter = timeline_genre_combo.split(',')
    query = 'SELECT * from movie_model'
    statement = SimpleStatement(query)
    results = db_session.execute(statement)
    # paging_state = results.paging_state    
    for row in results:                      #the cassandra driver auto paginates here
        # genres_list = []
        genres = row['genres']
        genres = genres.split(',')
        genres_list = list(map(lambda genre:genre.strip(),genres))
        intersection = set(genres_list).intersection(genre_filter)
        if len(intersection) > 0:            
            score = row['votes']
            movie_id_uuid = row['id']
            movie_id = str(movie_id_uuid)
            query = """
            INSERT INTO timelines (name,movie_id,rating,votes,title,plot,genres,poster)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            future = cassandra_session.execute_async(query,[timeline_genre_combo,movie_id_uuid,row['rating'],row['votes'],row['title'],row['plot'],row['genres'],row['poster']])
            def on_query_success(query_res):
                global count
                count += 1
                temp_dict = {
                    movie_id:score
                }
                r.zadd(timeline_genre_combo, temp_dict)
                print('movies_added:',count)

            def on_query_error(exception):
                print('failed to index %s',exception)
                return
        
            future.add_callbacks(on_query_success, on_query_error)            

get_movies_from_db_build_timeline(cassandra_session,timeline_genre_combo)
# query = 'select COUNT(*) from timelines where name =%s'
# rows = cassandra_session.execute(query,["Action,Comedy,Drama"])
# for row in rows:
#     print(row)
