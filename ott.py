from pyspark.sql import SparkSession
from pyspark.context import SparkContext
from pyspark.sql.functions import *
from pyspark.sql.types import *
import os
import pyspark
import subprocess


class Ott(object):
    """
    The class represents the implementation of mapreduce programming model

    """

    def __init__(self):
        """
        Initialize the file paths and create spark sessoin
        """
        hadoop_path = '/user/hduser/files/'
        hadoop_csv_path = '/user/hduser/inputfiles'
        subprocess.call(["hadoop", "fs", "-rm", "-r", hadoop_csv_path])
        # subprocess.call("hdfs", "dfs" "-mkdir", hadoop_path)
        subprocess.call(["hdfs", "dfs", "-mkdir", hadoop_csv_path])
        csv_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'files/')
        subprocess.call(["hdfs", "dfs", "-put", csv_path + 'MoviesOnStreamingPlatforms_updated.csv', hadoop_csv_path])
        subprocess.call(["hdfs", "dfs", "-put", csv_path + 'tv_shows.csv', hadoop_csv_path])
        subprocess.call(["hadoop", "fs", "-rm", "-r", hadoop_path])
        self.sc = SparkSession.builder.master('local[*]').appName("ottanalysis").config(
            "spark.driver.maxResultSize", "5g").getOrCreate()

    def read_csv(self, file_name):
        """
        read csv file from hdfs
        :param file_name: name of file
        :return: object
        """
        return self.sc.read.csv('hdfs://localhost:54310/user/hduser/inputfiles/' + file_name + '.csv', header=True)

    def change_data_type(self, df):
        """
        Modify data types of the variable available in dataframe
        :param df: dataframe
        :return:dataframe
        """
        df['IMDb'] = df['IMDb'].astype(float)
        df['Rotten Tomatoes'] = df['Rotten Tomatoes'].replace('%', '', regex=True).astype(float)

        df['Rotten Tomatoes'] = df['Rotten Tomatoes'].fillna(df['Rotten Tomatoes'].mean())
        df['IMDb'] = df['IMDb'].fillna(df['IMDb'].mean())

        return df

    def movies_data_cleansing(self):
        """
        Data cleaning of movies dataset
        :return: dataframe
        """
        pyspark_df = self.read_csv('MoviesOnStreamingPlatforms_updated')
        print(pyspark_df.summary().show())
        print(pyspark_df.printSchema())
        df = pyspark_df.toPandas()
        print(df.isnull().sum())
        df = df.drop(['ID', 'Age', 'Type', 'Directors', 'Genres', 'Country', 'Language', 'Runtime', 'Year'], axis=1)
        print(df.isnull().sum())

        df['Netflix'] = df['Netflix'].astype(float)
        df['Hulu'] = df['Hulu'].astype(int)
        df['Prime Video'] = df['Prime Video'].astype(int)
        df['Disney+'] = df['Disney+'].astype(int)
        df['Netflix'] = df['Netflix'].fillna(df['Netflix'].mode()[0])
        df['Netflix'] = df['Netflix'].astype(int)

        df = self.change_data_type(df)
        return df

    def tv_shows_data_cleansing(self):
        """
        Data cleaning of tv shows dataset
        :return:
        """
        pyspark_df = self.read_csv('tv_shows')
        print(pyspark_df.summary().show())
        print(pyspark_df.printSchema())
        df = pyspark_df.toPandas()
        print(df.isnull().sum())
        df = df.drop(['Age', 'Year', 'type'], axis=1)
        df['Hulu'] = df['Hulu'].astype(int)
        df['Prime Video'] = df['Prime Video'].astype(int)
        df['Disney+'] = df['Disney+'].astype(int)
        df['Netflix'] = df['Netflix'].astype(int)
        df = self.change_data_type(df)
        return df

    def sort_rdd(self, rdd):
        """
        Sort the rdd
        :param rdd: rdd
        :return:rdd
        """
        return rdd.sortBy(lambda new_rdd: new_rdd[1], ascending=False)

    def new_rating(self, rdd):
        """
        Create rdd of new rating by the combination of imdb and rotten tomatoes rating
        :param rdd: rdd
        :return: rdd
        """
        return self.sort_rdd(rdd.map(
            lambda rdd_row: (rdd_row['Title'], ((rdd_row['IMDb'] * 10) + rdd_row['Rotten Tomatoes']) / 2)))

    def imdb_rating(self, rdd):
        """
        new rdd with title and imdb rating and sort the rdd
        :param rdd:rdd
        :return: rdd
        """
        return self.sort_rdd(rdd.map(lambda rdd_row: (rdd_row['Title'], rdd_row['IMDb'])))

    def rotten_rating(self, rdd):
        """
        new rdd with title and rotten tomatoes and sort the rdd
        :param rdd: rdd
        :return: rdd
        """
        return self.sort_rdd(rdd.map(lambda rdd_row: (rdd_row['Title'], rdd_row['Rotten Tomatoes'])))

    def save_rdd_output(self, rdd1, rdd2, file_name):
        """
        Save rdd outputs in partition files
        :param rdd1: rdd
        :param rdd2:rdd
        :param file_name: name of file
        :return:
        """
        rdd1.saveAsTextFile('files/' + file_name + '_movies')
        rdd2.saveAsTextFile('files/' + file_name + '_tv_shows')

    def first_insight(self, movies_rdd, tv_shows_rdd):
        """
        Arrange movies according to new rating, imdb rating and rotten tomatoes rating
        :param movies_rdd:
        :param tv_shows_rdd:
        :return:
        """
        new_rating_movies_rdd = self.new_rating(movies_rdd)
        new_rating_tv_shows_rdd = self.new_rating(tv_shows_rdd)
        self.save_rdd_output(new_rating_movies_rdd, new_rating_tv_shows_rdd, 'first_insight_new_rating')

        imdb_rating_movies_order = self.imdb_rating(movies_rdd)
        imdb_rating_tv_shows_order = self.imdb_rating(tv_shows_rdd)
        self.save_rdd_output(imdb_rating_movies_order, imdb_rating_tv_shows_order, 'first_insight_imdb_rating')

        rotten_movies_order = self.rotten_rating(movies_rdd)
        rotten_tv_shows_order = self.rotten_rating(tv_shows_rdd)
        self.save_rdd_output(rotten_movies_order, rotten_tv_shows_order, 'first_insight_rotton_tomatoes')

    def single_ott(self, rdd):
        """
        Show the list of movies and tv shows available only on single OTT platform
        :param rdd:
        :return:
        """
        add_count_rdd = rdd.map(lambda rdd_rows: (
            rdd_rows['Title'], rdd_rows['Netflix'] + rdd_rows['Hulu'] + rdd_rows['Prime Video'] + rdd_rows['Disney+']))
        return add_count_rdd.filter(lambda rdd_rows: rdd_rows[1] == 1)

    def second_insight(self, movies_rdd, tv_shows_rdd):
        """
        Show the list of movies and tv shows available only on single OTT platform and save in partiion files
        :param movies_rdd: rdd having movies data
        :param tv_shows_rdd: rdd having tv shows data
        :return:
        """
        single_movie_rdd = self.single_ott(movies_rdd)
        single_tv_show_rdd = self.single_ott(tv_shows_rdd)
        self.save_rdd_output(single_movie_rdd, single_tv_show_rdd, 'second_insight')

    def ott_count(self, rdd):
        """
        Find which platform have highest count of movies and shows in each dataset
        :param rdd: rdd
        :return: rdd
        """
        final_name = 'Netflix'

        final_count = initial_count = rdd.filter(lambda rdd_rows: (rdd_rows['Netflix'] == 1)).count()
        initial_count = rdd.filter(lambda rdd_rows: rdd_rows['Hulu'] == 1).count()
        if initial_count > final_count:
            final_count = initial_count
            final_name = 'Hulu'
        initial_count = rdd.filter(lambda rdd_rows: rdd_rows['Prime Video'] == 1).count()
        if initial_count > final_count:
            final_count = initial_count
            final_name = 'Prime Video'
        initial_count = rdd.filter(lambda rdd_rows: rdd_rows['Disney+'] == 1).count()
        if initial_count > final_count:
            final_count = initial_count
            final_name = 'Disney+'

        return self.sc.sparkContext.parallelize([{final_name: final_count}], 1)

    def third_insight(self, movies_rdd, tv_shows_rdd):
        """
        Find which platform have highest count of movies and shows in each dataset and save in partition files
        :param movies_rdd: rdd having movies data
        :param tv_shows_rdd: rdd having tv shows data
        :return:
        """
        movies_platform = self.ott_count(movies_rdd)
        tv_shows_platform = self.ott_count(tv_shows_rdd)
        movies_platform.saveAsTextFile('files/third_insight_movies')
        tv_shows_platform.saveAsTextFile('files/third_insight_tv_shows')

    def analysis(self):
        """
        Call all analysis methods related to find insights
        :return:
        """
        movies_df = self.movies_data_cleansing()
        tv_shows_df = self.tv_shows_data_cleansing()

        # Create rdd for movies and tv shows
        movies_rdd = self.sc.createDataFrame(movies_df).rdd
        tv_shows_rdd = self.sc.createDataFrame(tv_shows_df).rdd

        self.first_insight(movies_rdd, tv_shows_rdd)
        self.second_insight(movies_rdd, tv_shows_rdd)
        self.third_insight(movies_rdd, tv_shows_rdd)

    def stop_spark(self):
        self.sc.stop()


ott_obj = Ott()
ott_obj.analysis()
ott_obj.stop_spark()

