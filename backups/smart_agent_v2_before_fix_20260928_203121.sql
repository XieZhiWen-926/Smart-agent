-- MySQL dump 10.13  Distrib 8.0.46, for Linux (x86_64)
--
-- Host: localhost    Database: smart_agent_v2
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `smart_agent_v2`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `smart_agent_v2` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `smart_agent_v2`;

--
-- Table structure for table `async_tasks`
--

DROP TABLE IF EXISTS `async_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `async_tasks` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ä»»åŠ¡ID',
  `task_id` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Celeryä»»åŠ¡ID',
  `task_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ç±»åž‹:csv_import/vectorize/report',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'pending' COMMENT 'çŠ¶æ€:pending/processing/completed/failed',
  `progress` int DEFAULT '0' COMMENT 'è¿›åº¦0-100',
  `result` json DEFAULT NULL COMMENT 'ä»»åŠ¡ç»“æžœ',
  `error_msg` text COLLATE utf8mb4_unicode_ci COMMENT 'å¤±è´¥åŽŸå› ',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æ›´æ–°æ—¶é—´',
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_id` (`task_id`),
  KEY `idx_task_id` (`task_id`),
  KEY `idx_type` (`task_type`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='å¼‚æ­¥ä»»åŠ¡çŠ¶æ€è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `async_tasks`
--

LOCK TABLES `async_tasks` WRITE;
/*!40000 ALTER TABLE `async_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `async_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `conversations`
--

DROP TABLE IF EXISTS `conversations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `conversations` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ä¼šè¯ID',
  `customer_id` int NOT NULL COMMENT 'å…³è”å®¢æˆ·ID',
  `title` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT 'æ–°ä¼šè¯' COMMENT 'ä¼šè¯æ ‡é¢˜',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æœ€åŽæ´»è·ƒæ—¶é—´',
  PRIMARY KEY (`id`),
  KEY `idx_customer` (`customer_id`),
  KEY `idx_created` (`created_at`),
  CONSTRAINT `fk_conv_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ä¼šè¯è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `conversations`
--

LOCK TABLES `conversations` WRITE;
/*!40000 ALTER TABLE `conversations` DISABLE KEYS */;
/*!40000 ALTER TABLE `conversations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `custom_tools`
--

DROP TABLE IF EXISTS `custom_tools`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `custom_tools` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'å·¥å…·ID',
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'å·¥å…·åç§°(è‹±æ–‡å‡½æ•°å)',
  `description` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'å·¥å…·æè¿°',
  `tool_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ç±»åž‹:builtin/map_amap/map_baidu/python_func/http_api',
  `parameters_schema` json NOT NULL COMMENT 'å‚æ•°JSON Schema',
  `config` json DEFAULT NULL COMMENT 'å·¥å…·é…ç½®JSON',
  `is_enabled` tinyint(1) DEFAULT '1' COMMENT 'æ˜¯å¦å¯ç”¨',
  `version` int DEFAULT '1' COMMENT 'ç‰ˆæœ¬å·',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æ›´æ–°æ—¶é—´',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  KEY `idx_name` (`name`),
  KEY `idx_type` (`tool_type`),
  KEY `idx_enabled` (`is_enabled`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='è‡ªå®šä¹‰å·¥å…·å®šä¹‰è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `custom_tools`
--

LOCK TABLES `custom_tools` WRITE;
/*!40000 ALTER TABLE `custom_tools` DISABLE KEYS */;
INSERT INTO `custom_tools` VALUES (1,'rag_summarize','ä»Žæ‰«åœ°æœºå™¨äººçŸ¥è¯†åº“ä¸­æ£€ç´¢ç›¸å…³èµ„æ–™å¹¶ç”Ÿæˆæ‘˜è¦å›žç­”ã€‚å½“ç”¨æˆ·è¯¢é—®äº§å“åŠŸèƒ½ã€æ•…éšœæŽ’é™¤ã€ç»´æŠ¤ä¿å…»ã€é€‰è´­å»ºè®®ç­‰çŸ¥è¯†ç±»é—®é¢˜æ—¶ä½¿ç”¨ã€‚','builtin','{\"type\": \"object\", \"required\": [\"query\"], \"properties\": {\"query\": {\"type\": \"string\", \"description\": \"ç”¨æˆ·çš„é—®é¢˜\"}}}','{\"source\": \"chroma_knowledge_base\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(2,'amap_geocode','é«˜å¾·åœ°å›¾åœ°ç†ç¼–ç ï¼šå°†è¯¦ç»†åœ°å€è½¬æ¢ä¸ºç»çº¬åº¦åæ ‡ã€‚å½“éœ€è¦èŽ·å–æŸä¸ªåœ°å€çš„ç»çº¬åº¦æ—¶ä½¿ç”¨ã€‚','map_amap','{\"type\": \"object\", \"required\": [\"address\"], \"properties\": {\"city\": {\"type\": \"string\", \"description\": \"åŸŽå¸‚åï¼Œå¯é€‰\"}, \"address\": {\"type\": \"string\", \"description\": \"è¯¦ç»†åœ°å€ï¼Œå¦‚åŒ—äº¬å¸‚æœé˜³åŒºæœ›äº¬SOHO\"}}}','{\"api_endpoint\": \"geocode/geo\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(3,'amap_regeocode','é«˜å¾·åœ°å›¾é€†åœ°ç†ç¼–ç ï¼šå°†ç»çº¬åº¦åæ ‡è½¬æ¢ä¸ºåœ°å€æè¿°ã€‚å½“éœ€è¦æ ¹æ®åæ ‡èŽ·å–åœ°å€ä¿¡æ¯æ—¶ä½¿ç”¨ã€‚','map_amap','{\"type\": \"object\", \"required\": [\"longitude\", \"latitude\"], \"properties\": {\"latitude\": {\"type\": \"string\", \"description\": \"çº¬åº¦\"}, \"longitude\": {\"type\": \"string\", \"description\": \"ç»åº¦\"}}}','{\"api_endpoint\": \"geocode/regeo\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(4,'amap_weather','é«˜å¾·åœ°å›¾å¤©æ°”æŸ¥è¯¢ï¼šèŽ·å–æŒ‡å®šåŸŽå¸‚çš„å®žæ—¶å¤©æ°”å’Œé¢„æŠ¥ä¿¡æ¯ã€‚å½“ç”¨æˆ·è¯¢é—®å¤©æ°”æƒ…å†µæ—¶ä½¿ç”¨ï¼Œè¿”å›žçœŸå®žå¤©æ°”æ•°æ®ã€‚','map_amap','{\"type\": \"object\", \"required\": [\"city\"], \"properties\": {\"city\": {\"type\": \"string\", \"description\": \"åŸŽå¸‚åï¼Œå¦‚åŒ—äº¬ã€ä¸Šæµ·\"}}}','{\"extensions\": \"all\", \"api_endpoint\": \"weather/weatherInfo\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(5,'amap_around_search','é«˜å¾·åœ°å›¾å‘¨è¾¹POIæœç´¢ï¼šæœç´¢æŒ‡å®šä½ç½®é™„è¿‘çš„åœ°ç‚¹ï¼ˆå¦‚ç»´ä¿®ç‚¹ã€é—¨åº—ï¼‰ã€‚å½“ç”¨æˆ·éœ€è¦æŸ¥æ‰¾é™„è¿‘çš„æœåŠ¡ç½‘ç‚¹æ—¶ä½¿ç”¨ã€‚','map_amap','{\"type\": \"object\", \"required\": [\"keyword\", \"location\"], \"properties\": {\"radius\": {\"type\": \"integer\", \"description\": \"æœç´¢åŠå¾„ç±³ï¼Œé»˜è®¤3000\"}, \"keyword\": {\"type\": \"string\", \"description\": \"æœç´¢å…³é”®è¯ï¼Œå¦‚æ‰«åœ°æœºå™¨äººç»´ä¿®\"}, \"location\": {\"type\": \"string\", \"description\": \"ä¸­å¿ƒç‚¹åæ ‡ï¼Œæ ¼å¼ ç»åº¦,çº¬åº¦\"}}}','{\"api_endpoint\": \"place/around\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(6,'baidu_geocode','ç™¾åº¦åœ°å›¾åœ°ç†ç¼–ç ï¼šå°†åœ°å€è½¬æ¢ä¸ºç™¾åº¦åæ ‡ç³»ç»çº¬åº¦ã€‚å½“éœ€è¦ä½¿ç”¨ç™¾åº¦åœ°å›¾æœåŠ¡èŽ·å–åæ ‡æ—¶ä½¿ç”¨ã€‚','map_baidu','{\"type\": \"object\", \"required\": [\"address\"], \"properties\": {\"address\": {\"type\": \"string\", \"description\": \"è¯¦ç»†åœ°å€\"}}}','{\"api_endpoint\": \"geocoder/v2/\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54'),(7,'baidu_weather','ç™¾åº¦åœ°å›¾å¤©æ°”æŸ¥è¯¢ï¼šèŽ·å–æŒ‡å®šåŸŽå¸‚çš„å¤©æ°”ä¿¡æ¯ã€‚å½“ç”¨æˆ·è¯¢é—®å¤©æ°”ä¸”åå¥½ç™¾åº¦åœ°å›¾æ•°æ®æ—¶ä½¿ç”¨ã€‚','map_baidu','{\"type\": \"object\", \"required\": [\"district_id\"], \"properties\": {\"district_id\": {\"type\": \"string\", \"description\": \"åŒºåŽ¿IDæˆ–åŸŽå¸‚å\"}}}','{\"api_endpoint\": \"weather/v1/\"}',1,1,'2026-09-28 13:50:54','2026-09-28 13:50:54');
/*!40000 ALTER TABLE `custom_tools` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customers`
--

DROP TABLE IF EXISTS `customers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customers` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'å®¢æˆ·ID',
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'å®¢æˆ·å§“å',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'æ‰‹æœºå·',
  `city` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT 'æ‰€åœ¨åŸŽå¸‚',
  `address` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT 'è¯¦ç»†åœ°å€',
  `longitude` float DEFAULT NULL COMMENT 'åœ°å€ç»åº¦(é«˜å¾·åæ ‡ç³»)',
  `latitude` float DEFAULT NULL COMMENT 'åœ°å€çº¬åº¦(é«˜å¾·åæ ‡ç³»)',
  `member_level` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'æ™®é€š' COMMENT 'ä¼šå‘˜ç­‰çº§:æ™®é€š/é“¶å¡/é‡‘å¡/é’»çŸ³',
  `product_model` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT 'è´­ä¹°çš„æ‰«åœ°æœºå™¨äººåž‹å·',
  `purchase_date` datetime DEFAULT NULL COMMENT 'è´­ä¹°æ—¥æœŸ',
  `remark` text COLLATE utf8mb4_unicode_ci COMMENT 'å¤‡æ³¨',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æ›´æ–°æ—¶é—´',
  PRIMARY KEY (`id`),
  UNIQUE KEY `phone` (`phone`),
  KEY `idx_phone` (`phone`),
  KEY `idx_city` (`city`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='å®¢æˆ·ä¿¡æ¯è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customers`
--

LOCK TABLES `customers` WRITE;
/*!40000 ALTER TABLE `customers` DISABLE KEYS */;
INSERT INTO `customers` VALUES (1,'å¼ ä¸‰','13800138001','æ·±åœ³','æ·±åœ³å¸‚å—å±±åŒºç§‘æŠ€å›­',NULL,NULL,'é‡‘å¡','æ™ºæ‰«é€šPro X1',NULL,'å¯¹å™ªéŸ³æ•æ„Ÿï¼Œåå¥½é™éŸ³æ¨¡å¼','2026-09-28 13:50:54','2026-09-28 13:50:54'),(2,'æŽå››','13800138002','åˆè‚¥','åˆè‚¥å¸‚èœ€å±±åŒºæ”¿åŠ¡åŒº',NULL,NULL,'æ™®é€š','æ™ºæ‰«é€šLite S2',NULL,'','2026-09-28 13:50:54','2026-09-28 13:50:54'),(3,'çŽ‹äº”','13800138003','æ­å·ž','æ­å·žå¸‚è¥¿æ¹–åŒºæ–‡ä¸‰è·¯',NULL,NULL,'é“¶å¡','æ™ºæ‰«é€šMax M3',NULL,'å…»å® ç‰©ï¼Œéœ€è¦é¢‘ç¹æ¸…ç†æ¯›å‘','2026-09-28 13:50:54','2026-09-28 13:50:54');
/*!40000 ALTER TABLE `customers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `datasets`
--

DROP TABLE IF EXISTS `datasets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `datasets` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'æ•°æ®é›†ID',
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'æ•°æ®é›†åç§°',
  `description` text COLLATE utf8mb4_unicode_ci COMMENT 'æ•°æ®é›†æè¿°',
  `table_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'å®žé™…å­˜å‚¨çš„MySQLè¡¨å',
  `source_file` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT 'åŽŸå§‹CSVæ–‡ä»¶å',
  `row_count` int DEFAULT '0' COMMENT 'æ•°æ®è¡Œæ•°',
  `column_count` int DEFAULT '0' COMMENT 'åˆ—æ•°',
  `columns_meta` json NOT NULL COMMENT 'åˆ—å…ƒæ•°æ®(å«ä¸­æ–‡åˆ—åæ˜ å°„)',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'pending' COMMENT 'çŠ¶æ€:pending/processing/completed/failed',
  `error_msg` text COLLATE utf8mb4_unicode_ci COMMENT 'å¤±è´¥åŽŸå› ',
  `created_by` int DEFAULT NULL COMMENT 'ä¸Šä¼ è€…ç”¨æˆ·ID',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æ›´æ–°æ—¶é—´',
  PRIMARY KEY (`id`),
  UNIQUE KEY `table_name` (`table_name`),
  KEY `idx_status` (`status`),
  KEY `idx_table` (`table_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='æ•°æ®é›†å…ƒæ•°æ®è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `datasets`
--

LOCK TABLES `datasets` WRITE;
/*!40000 ALTER TABLE `datasets` DISABLE KEYS */;
/*!40000 ALTER TABLE `datasets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `long_term_memories`
--

DROP TABLE IF EXISTS `long_term_memories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `long_term_memories` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'è®°å¿†ID',
  `customer_id` int NOT NULL COMMENT 'å…³è”å®¢æˆ·ID',
  `memory_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ç±»åž‹:fact/preference/summary',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'è®°å¿†å†…å®¹',
  `importance` int DEFAULT '5' COMMENT 'é‡è¦æ€§1-10',
  `embedding` json DEFAULT NULL COMMENT 'å‘é‡åµŒå…¥(JSONæ•°ç»„)',
  `source_message_id` int DEFAULT NULL COMMENT 'æ¥æºæ¶ˆæ¯ID',
  `last_used_at` datetime DEFAULT NULL COMMENT 'æœ€åŽä½¿ç”¨æ—¶é—´',
  `use_count` int DEFAULT '0' COMMENT 'ä½¿ç”¨æ¬¡æ•°',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'æ›´æ–°æ—¶é—´',
  PRIMARY KEY (`id`),
  KEY `idx_customer` (`customer_id`),
  KEY `idx_type` (`memory_type`),
  KEY `idx_created` (`created_at`),
  CONSTRAINT `fk_mem_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='é•¿æœŸè®°å¿†è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `long_term_memories`
--

LOCK TABLES `long_term_memories` WRITE;
/*!40000 ALTER TABLE `long_term_memories` DISABLE KEYS */;
/*!40000 ALTER TABLE `long_term_memories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `messages`
--

DROP TABLE IF EXISTS `messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `messages` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'æ¶ˆæ¯ID',
  `conversation_id` int NOT NULL COMMENT 'å…³è”ä¼šè¯ID',
  `role` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'è§’è‰²:user/assistant/tool/system',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'æ¶ˆæ¯å†…å®¹',
  `token_count` int DEFAULT '0' COMMENT 'æ¶ˆè€—tokenæ•°',
  `tool_name` varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'å·¥å…·è°ƒç”¨æ—¶çš„å·¥å…·å',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  PRIMARY KEY (`id`),
  KEY `idx_conversation` (`conversation_id`),
  KEY `idx_role` (`role`),
  KEY `idx_created` (`created_at`),
  CONSTRAINT `fk_msg_conversation` FOREIGN KEY (`conversation_id`) REFERENCES `conversations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='æ¶ˆæ¯è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `messages`
--

LOCK TABLES `messages` WRITE;
/*!40000 ALTER TABLE `messages` DISABLE KEYS */;
/*!40000 ALTER TABLE `messages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'ç”¨æˆ·ID',
  `username` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ç”¨æˆ·å',
  `hashed_password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'å¯†ç å“ˆå¸Œ(bcrypt)',
  `full_name` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT '' COMMENT 'çœŸå®žå§“å',
  `role` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'admin' COMMENT 'è§’è‰²:admin/operator',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'æ˜¯å¦å¯ç”¨',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'åˆ›å»ºæ—¶é—´',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='ç³»ç»Ÿç”¨æˆ·è¡¨';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','$2b$12$cFwU6TiGNS/GfBAahsC/3uUyohvxLicsSKKNinrW65kCydexXaSqW','系统管理员','admin',1,'2026-09-28 12:24:40'),(3,'verify_qa_01','$2b$12$/ln3WfqkYD2MnmJQVulJWO5bi8A8vnWzA6ZUgQK3LXlXgi0GPYW7W','验证用账号','operator',1,'2026-09-28 12:29:57');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-28 20:31:25
