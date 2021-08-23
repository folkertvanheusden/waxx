-- MySQL dump 10.17  Distrib 10.3.17-MariaDB, for debian-linux-gnu (x86_64)
--
-- Host: localhost    Database: waxx
-- ------------------------------------------------------
-- Server version	10.3.17-MariaDB-0+deb10u1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `moves`
--

DROP TABLE IF EXISTS `moves`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `moves` (
  `results_id` int(11) NOT NULL,
  `move_nr` int(4) DEFAULT NULL,
  `fen` varchar(128) DEFAULT NULL,
  `move` varchar(5) DEFAULT NULL,
  `took` double DEFAULT NULL,
  `score` int(11) DEFAULT NULL,
  `is_p1` int(1) DEFAULT NULL,
  KEY `results_id` (`results_id`),
  CONSTRAINT `moves_ibfk_1` FOREIGN KEY (`results_id`) REFERENCES `results` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `players`
--

DROP TABLE IF EXISTS `players`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `players` (
  `user` varchar(64) NOT NULL,
  `password` varchar(64) DEFAULT NULL,
  `rating` double DEFAULT 1000,
  `w` int(8) DEFAULT 0,
  `d` int(8) DEFAULT 0,
  `l` int(8) DEFAULT 0,
  `failure_count` int(8) DEFAULT 0,
  `author` varchar(128) DEFAULT NULL,
  `engine` varchar(128) DEFAULT NULL,
  `last_game` datetime DEFAULT NULL,
  `rd` double DEFAULT NULL,
  PRIMARY KEY (`user`)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `results`
--

DROP TABLE IF EXISTS `results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `results` (
  `ts` datetime DEFAULT NULL,
  `p1` varchar(64) DEFAULT NULL,
  `e1` varchar(128) DEFAULT NULL,
  `t1` double DEFAULT NULL,
  `p2` varchar(64) DEFAULT NULL,
  `e2` varchar(128) DEFAULT NULL,
  `t2` double DEFAULT NULL,
  `result` varchar(7) DEFAULT NULL,
  `adjudication` varchar(128) DEFAULT NULL,
  `plies` int(11) DEFAULT NULL,
  `tpm` int(11) DEFAULT NULL,
  `pgn` text DEFAULT NULL,
  `md5` char(32) DEFAULT NULL,
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `score` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=213504 DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2019-12-10 20:04:51
