-- ============================================================================
-- SNOWFLAKE_SETUP.sql — One-time data setup for the TravelDemo A2A demo
--
-- Creates the full data infrastructure for the travel booking demo:
--   - TRAVEL_DEMO database and BOOKING schema
--   - HOTELS, HOTEL_REVIEWS, FLIGHTS, FLIGHT_FEEDBACK tables with sample data
--   - BOOKING_MODELS stage (for Cortex Analyst semantic model YAMLs)
--   - HOTEL_REVIEWS_SEARCH and FLIGHT_FEEDBACK_SEARCH Cortex Search services
--   - HOTELS_BOOKING_AGENT and FLIGHTS_BOOKING_AGENT Cortex Agents
--
-- Prerequisites:
--   - Upload hotels_semantic.yaml and flights_semantic.yaml to @BOOKING_MODELS
--     after running this script (see instructions at the bottom)
--   - COMPUTE_WH warehouse must exist
--
-- Replace <AGENT_DATABASE> and <AGENT_SCHEMA> below if you prefer a different
-- location for the SPCS image repository. The agent data always lives in
-- TRAVEL_DEMO.BOOKING.
-- ============================================================================

USE ROLE SYSADMIN;

-- ============================================================================
-- 1. DATABASE AND SCHEMA
-- ============================================================================

CREATE DATABASE IF NOT EXISTS TRAVEL_DEMO;
CREATE SCHEMA IF NOT EXISTS TRAVEL_DEMO.BOOKING;

USE DATABASE TRAVEL_DEMO;
USE SCHEMA BOOKING;

-- ============================================================================
-- 2. TABLES
-- ============================================================================

CREATE OR REPLACE TABLE TRAVEL_DEMO.BOOKING.HOTELS (
    HOTEL_ID            VARCHAR(20)     NOT NULL,
    HOTEL_NAME          VARCHAR(100)    NOT NULL,
    CITY                VARCHAR(50)     NOT NULL,
    COUNTRY             VARCHAR(50)     NOT NULL,
    STAR_RATING         NUMBER(1,0)     NOT NULL,
    PRICE_PER_NIGHT     NUMBER(8,2)     NOT NULL,
    ROOM_TYPE           VARCHAR(30)     NOT NULL,
    AVAILABLE_ROOMS     NUMBER(5,0)     NOT NULL,
    AMENITIES           VARCHAR(500),
    CHECK_IN_DATE       DATE,
    CHECK_OUT_DATE      DATE,
    BOOKING_STATUS      VARCHAR(20)     NOT NULL,
    GUEST_RATING        FLOAT,
    CANCELLATION_POLICY VARCHAR(30),
    LOYALTY_TIER        VARCHAR(20),
    PRIMARY KEY (HOTEL_ID)
);

CREATE OR REPLACE TABLE TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS (
    REVIEW_ID       VARCHAR(20)     NOT NULL,
    HOTEL_ID        VARCHAR(20)     NOT NULL,
    GUEST_NAME      VARCHAR(100),
    REVIEW_DATE     DATE,
    REVIEW_TEXT     VARCHAR(2000)   NOT NULL,
    SENTIMENT       VARCHAR(20),
    RATING          NUMBER(2,0),
    PRIMARY KEY (REVIEW_ID)
);

CREATE OR REPLACE TABLE TRAVEL_DEMO.BOOKING.FLIGHTS (
    FLIGHT_ID           VARCHAR(20)     NOT NULL,
    AIRLINE             VARCHAR(50)     NOT NULL,
    FLIGHT_NUMBER       VARCHAR(10)     NOT NULL,
    ORIGIN_CITY         VARCHAR(50)     NOT NULL,
    ORIGIN_CODE         VARCHAR(5)      NOT NULL,
    DESTINATION_CITY    VARCHAR(50)     NOT NULL,
    DESTINATION_CODE    VARCHAR(5)      NOT NULL,
    DEPARTURE_TIME      TIMESTAMP       NOT NULL,
    ARRIVAL_TIME        TIMESTAMP       NOT NULL,
    DURATION_MINUTES    NUMBER(5,0)     NOT NULL,
    SEAT_CLASS          VARCHAR(20)     NOT NULL,
    PRICE               NUMBER(8,2)     NOT NULL,
    AVAILABLE_SEATS     NUMBER(5,0)     NOT NULL,
    BOOKING_STATUS      VARCHAR(20)     NOT NULL,
    DELAY_MINUTES       NUMBER(5,0)     DEFAULT 0,
    PRIMARY KEY (FLIGHT_ID)
);

CREATE OR REPLACE TABLE TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK (
    FEEDBACK_ID     VARCHAR(20)     NOT NULL,
    FLIGHT_ID       VARCHAR(20)     NOT NULL,
    PASSENGER_NAME  VARCHAR(100),
    FEEDBACK_DATE   DATE,
    FEEDBACK_TEXT   VARCHAR(2000)   NOT NULL,
    SENTIMENT       VARCHAR(20),
    RATING          NUMBER(2,0),
    PRIMARY KEY (FEEDBACK_ID)
);

-- ============================================================================
-- 3. SAMPLE DATA — HOTELS
-- ============================================================================

INSERT INTO TRAVEL_DEMO.BOOKING.HOTELS VALUES
('H001', 'The Grand Paris',       'Paris',      'France',      5, 450.00, 'Suite',      3,  'spa,pool,fine dining,concierge,free wifi',                  '2026-04-01', '2026-04-07', 'available', 9.2, 'free_cancellation', 'platinum'),
('H002', 'Hotel Lumiere',         'Paris',      'France',      4, 180.00, 'Deluxe',    12,  'free wifi,breakfast,concierge',                             '2026-04-01', '2026-04-05', 'available', 8.5, '24h_notice',        'gold'),
('H003', 'Tokyo Garden Inn',      'Tokyo',      'Japan',       4, 220.00, 'Standard',   8,  'onsen,free wifi,gym,restaurant',                            '2026-04-10', '2026-04-15', 'available', 8.8, 'free_cancellation', 'gold'),
('H004', 'Sakura Suite Hotel',    'Tokyo',      'Japan',       5, 680.00, 'Penthouse',  1,  'private pool,butler,spa,helipad',                           '2026-04-10', '2026-04-15', 'limited',   9.7, 'non_refundable',    'platinum'),
('H005', 'Manhattan Skyhigh',     'New York',   'USA',         5, 550.00, 'Suite',      5,  'rooftop bar,gym,spa,concierge,free wifi',                   '2026-04-05', '2026-04-10', 'available', 9.0, 'free_cancellation', 'platinum'),
('H006', 'Brooklyn Budget Inn',   'New York',   'USA',         3,  95.00, 'Standard',  20,  'free wifi,24h reception',                                   '2026-04-05', '2026-04-10', 'available', 7.2, 'free_cancellation', 'standard'),
('H007', 'The London Clubhouse',  'London',     'UK',          5, 490.00, 'Deluxe',     4,  'afternoon tea,library,spa,concierge',                       '2026-04-08', '2026-04-12', 'available', 9.4, '24h_notice',        'platinum'),
('H008', 'Shoreditch Boutique',   'London',     'UK',          4, 175.00, 'Standard',  15,  'rooftop bar,free wifi,gym',                                 '2026-04-08', '2026-04-12', 'available', 8.3, 'free_cancellation', 'silver'),
('H009', 'Colosseum View Hotel',  'Rome',       'Italy',       4, 240.00, 'Deluxe',     9,  'rooftop pool,free wifi,breakfast,spa',                      '2026-04-20', '2026-04-25', 'available', 8.9, 'free_cancellation', 'gold'),
('H010', 'Dubai Oasis Tower',     'Dubai',      'UAE',         5, 820.00, 'Suite',      2,  'infinity pool,beach access,butler,spa,helicopter transfer', '2026-04-15', '2026-04-20', 'limited',   9.6, 'non_refundable',    'platinum'),
('H011', 'Sydney Harbour Lodge',  'Sydney',     'Australia',   4, 310.00, 'Deluxe',     7,  'harbour view,pool,free wifi,gym,breakfast',                 '2026-05-01', '2026-05-07', 'available', 8.7, 'free_cancellation', 'gold'),
('H012', 'Bali Zen Resort',       'Bali',       'Indonesia',   5, 380.00, 'Suite',      6,  'private villa,infinity pool,spa,yoga classes,free wifi',    '2026-04-25', '2026-05-02', 'available', 9.5, '24h_notice',        'platinum'),
('H013', 'Amsterdam Canal House', 'Amsterdam',  'Netherlands', 4, 195.00, 'Standard',  11,  'canal view,free wifi,breakfast,bicycle rental',             '2026-05-05', '2026-05-10', 'available', 8.6, 'free_cancellation', 'gold'),
('H014', 'Santorini Clifftop',    'Santorini',  'Greece',      5, 720.00, 'Penthouse',  2,  'caldera view,infinity pool,private jacuzzi,butler',         '2026-06-01', '2026-06-07', 'limited',   9.8, 'non_refundable',    'platinum'),
('H015', 'Bangkok City Center',   'Bangkok',    'Thailand',    3,  85.00, 'Standard',  25,  'free wifi,pool,restaurant,gym',                             '2026-04-12', '2026-04-18', 'available', 7.8, 'free_cancellation', 'standard');

-- ============================================================================
-- 4. SAMPLE DATA — HOTEL REVIEWS
-- ============================================================================

INSERT INTO TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS VALUES
('R001', 'H001', 'Marie Dubois',         '2026-03-15', 'Absolutely magnificent stay at The Grand Paris! The spa was world-class and the butler service was impeccable. The room had stunning views of the Eiffel Tower. Worth every penny for a special occasion.',                                                                                     'positive', 10),
('R002', 'H001', 'James Chen',           '2026-02-28', 'The Grand Paris lived up to its reputation. Breakfast was extraordinary, staff were attentive without being intrusive. The suite was spacious and beautifully appointed. Will definitely return.',                                                                                               'positive',  9),
('R003', 'H002', 'Sarah Miller',         '2026-03-10', 'Hotel Lumiere is a solid choice for budget-conscious travelers. The breakfast was included and surprisingly good. Location was excellent near the Louvre. Room was small but clean and well-maintained.',                                                                                        'neutral',   8),
('R004', 'H002', 'Tom Wilson',           '2026-02-20', 'Decent hotel but nothing special. The wifi was slow and the room had noise from the street. Staff were friendly and helpful when we had issues. Good value for the location.',                                                                                                                   'neutral',   7),
('R005', 'H003', 'Yuki Tanaka',          '2026-03-20', 'Tokyo Garden Inn exceeded all expectations. The onsen bath was the highlight of our trip. Incredibly peaceful after a day of sightseeing. The staff were exceptionally kind and helpful with local recommendations.',                                                                           'positive',  9),
('R006', 'H004', 'Robert Kim',           '2026-03-05', 'Sakura Suite Hotel is unparalleled luxury. The private pool, the personalized butler service, and the panoramic views of Tokyo made our honeymoon unforgettable. An experience unlike anything else.',                                                                                          'positive', 10),
('R007', 'H005', 'Emma Thompson',        '2026-03-12', 'Manhattan Skyhigh has the best rooftop bar in the city. The view is incredible and the cocktails are amazing. The room was modern and well-equipped. Gym was well-maintained. Great for a business trip.',                                                                                      'positive',  9),
('R008', 'H006', 'David Park',           '2026-03-18', 'Brooklyn Budget Inn is exactly what you expect at this price point. Clean, functional, and well-located for exploring Brooklyn. The 24h reception was helpful. No frills but honest value.',                                                                                                   'neutral',   7),
('R009', 'H007', 'Isabella Ross',        '2026-03-08', 'The London Clubhouse is a true classic. The afternoon tea ritual was delightful, the library atmosphere was cozy, and the staff treated us like royalty. Perfect for a romantic getaway in the heart of London.',                                                                               'positive', 10),
('R010', 'H007', 'Michael Brown',        '2026-02-15', 'Service was impeccable at The London Clubhouse but the prices are steep even by London standards. The spa was excellent though rooms on the street side were surprisingly noisy at night.',                                                                                                     'neutral',   8),
('R011', 'H008', 'Alice Green',          '2026-03-22', 'Shoreditch Boutique is very trendy and the rooftop bar has fantastic views. However, the rooms are a bit small and the walls are thin. Great for a social stay, not ideal for a quiet rest.',                                                                                                  'neutral',   7),
('R012', 'H009', 'Marco Rossi',          '2026-03-25', 'Colosseum View Hotel is perfectly located with stunning rooftop views. The breakfast was delicious and the staff organized excellent local tours. The spa needs upgrading but overall a wonderful stay.',                                                                                       'positive',  9),
('R013', 'H010', 'Zhang Wei',            '2026-03-01', 'Dubai Oasis Tower is the pinnacle of luxury. The infinity pool overlooking the marina was breathtaking. The butler prepared our schedule each morning. The helicopter transfer from the airport was a surreal and unforgettable touch.',                                                        'positive', 10),
('R014', 'H010', 'Priya Sharma',         '2026-02-10', 'Dubai Oasis Tower is incredibly opulent but the non-refundable policy is too rigid. Had to change dates due to a work emergency and lost the full amount. The stay itself was flawless but the policy needs revisiting for loyal guests.',                                                     'negative',  6),
('R015', 'H011', 'Jake Murphy',          '2026-03-15', 'Sydney Harbour Lodge has the best breakfast view imaginable. Waking up to the harbour bridge and opera house was priceless. The staff were friendly and the pool area was well-maintained throughout our stay.',                                                                                'positive',  9),
('R016', 'H012', 'Nia Williams',         '2026-03-28', 'Bali Zen Resort was the most relaxing holiday of my life. The private villa, the infinity pool, the daily yoga classes, and the incredible spa treatments all combined for a perfect retreat. Cannot recommend enough.',                                                                        'positive', 10),
('R017', 'H013', 'Lars Eriksson',        '2026-03-20', 'Amsterdam Canal House is perfectly charming. Cycling along the canals with the included bicycles was the highlight of our trip. The canal-view room was a great choice. Breakfast was simple but fresh and satisfying.',                                                                       'positive',  8),
('R018', 'H014', 'Sofia Papadopoulos',   '2026-03-10', 'Santorini Clifftop is the most beautiful hotel I have ever stayed at. The caldera views from the private jacuzzi at sunset were absolutely magical. Expensive but completely worth every euro.',                                                                                               'positive', 10),
('R019', 'H015', 'Chen Jing',            '2026-03-18', 'Bangkok City Center is excellent value for money. Clean pool, decent gym, good restaurant with authentic Thai food. The location in the business district is convenient for meetings. Basic but reliable.',                                                                                    'neutral',   8),
('R020', 'H005', 'Olivia Hart',          '2026-02-25', 'The Manhattan Skyhigh spa was disappointing for a 5-star hotel. Treatment rooms were small and the menu limited. The rooftop bar and views more than compensated, and the room itself was fantastic. Mixed overall experience.',                                                               'neutral',   7);

-- ============================================================================
-- 5. SAMPLE DATA — FLIGHTS
-- ============================================================================

INSERT INTO TRAVEL_DEMO.BOOKING.FLIGHTS VALUES
('FL001', 'Delta',             'DL401',  'New York',    'JFK', 'London',       'LHR', '2026-04-01 08:00:00', '2026-04-01 20:00:00', 420, 'economy',         380.00,  45, 'available',  0),
('FL002', 'Delta',             'DL401',  'New York',    'JFK', 'London',       'LHR', '2026-04-01 08:00:00', '2026-04-01 20:00:00', 420, 'business',       2800.00,   8, 'limited',    0),
('FL003', 'British Airways',   'BA177',  'London',      'LHR', 'New York',     'JFK', '2026-04-02 11:30:00', '2026-04-02 14:45:00', 435, 'economy',         420.00,  32, 'available',  0),
('FL004', 'Emirates',          'EK201',  'New York',    'JFK', 'Dubai',        'DXB', '2026-04-03 22:15:00', '2026-04-04 19:30:00', 795, 'first',          8500.00,   4, 'available',  0),
('FL005', 'Lufthansa',         'LH400',  'Frankfurt',   'FRA', 'New York',     'JFK', '2026-04-04 13:00:00', '2026-04-04 15:45:00', 525, 'premium_economy',1200.00,  18, 'available',  0),
('FL006', 'Singapore Airlines','SQ321',  'Singapore',   'SIN', 'London',       'LHR', '2026-04-05 00:05:00', '2026-04-05 06:25:00', 740, 'business',       4200.00,   6, 'available',  0),
('FL007', 'Japan Airlines',    'JL44',   'Tokyo',       'NRT', 'Los Angeles',  'LAX', '2026-04-06 17:20:00', '2026-04-06 11:00:00', 580, 'economy',         520.00,  28, 'available', 35),
('FL008', 'Air France',        'AF83',   'Paris',       'CDG', 'Tokyo',        'NRT', '2026-04-07 10:10:00', '2026-04-08 06:30:00', 680, 'economy',         590.00,   0, 'sold_out',   0),
('FL009', 'Qatar Airways',     'QR2',    'Doha',        'DOH', 'New York',     'JFK', '2026-04-08 02:15:00', '2026-04-08 08:30:00', 795, 'business',       3900.00,  12, 'available',  0),
('FL010', 'United',            'UA880',  'San Francisco','SFO','Tokyo',        'NRT', '2026-04-09 11:55:00', '2026-04-10 15:30:00', 575, 'economy',         480.00,  55, 'available',  0),
('FL011', 'Cathay Pacific',    'CX883',  'Hong Kong',   'HKG', 'Sydney',       'SYD', '2026-04-10 22:30:00', '2026-04-11 08:45:00', 495, 'business',       2200.00,  10, 'available',  0),
('FL012', 'Delta',             'DL1',    'New York',    'JFK', 'Los Angeles',  'LAX', '2026-04-11 07:00:00', '2026-04-11 10:15:00', 315, 'economy',         180.00,  80, 'available',  0),
('FL013', 'Lufthansa',         'LH757',  'Munich',      'MUC', 'Singapore',    'SIN', '2026-04-12 14:20:00', '2026-04-13 07:00:00', 700, 'premium_economy',1650.00,  14, 'available',  0),
('FL014', 'Emirates',          'EK77',   'Dubai',       'DXB', 'Sydney',       'SYD', '2026-04-13 09:45:00', '2026-04-14 06:15:00', 810, 'economy',         620.00,  22, 'available',  0),
('FL015', 'British Airways',   'BA293',  'London',      'LHR', 'Tokyo',        'NRT', '2026-04-14 12:30:00', '2026-04-15 08:20:00', 710, 'business',       4800.00,   3, 'limited',  120);

-- ============================================================================
-- 6. SAMPLE DATA — FLIGHT FEEDBACK
-- ============================================================================

INSERT INTO TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK VALUES
('FB001', 'FL001', 'Alice Johnson',       '2026-03-20', 'Delta flight DL401 to London was comfortable and on time. The economy seats had decent legroom compared to competitors. Food was mediocre but the entertainment system was excellent. Crew were professional and attentive throughout the flight.',                                              'positive',  8),
('FB002', 'FL002', 'Benjamin Lee',        '2026-03-21', 'Delta business class to London was worth every cent. The lie-flat seats were comfortable and the food was genuinely restaurant quality. The lounge access at JFK was a great bonus. Will fly Delta business class again without hesitation.',                                                   'positive',  9),
('FB003', 'FL003', 'Claire Dumas',        '2026-03-22', 'British Airways from Heathrow was impeccable. The flight attendants were courteous and food quality in economy exceeded expectations. Slight turbulence over the Atlantic but handled professionally. Arrived on schedule.',                                                                    'positive',  8),
('FB004', 'FL004', 'David Mitchell',      '2026-03-23', 'Emirates first class is in a league of its own. The private suite, the gourmet dining, the bar on the upper deck, and the chauffeur service made the journey feel like the destination itself. Truly an unparalleled travel experience.',                                                     'positive', 10),
('FB005', 'FL005', 'Eva Braun',           '2026-03-24', 'Lufthansa premium economy was comfortable but overpriced. The extra legroom was welcome but the food was standard economy quality. The Frankfurt lounge access was a highlight. Mixed feelings overall — value for money is questionable.',                                                    'neutral',   7),
('FB006', 'FL006', 'Frank Lim',           '2026-03-25', 'Singapore Airlines business class is consistently world-class. The KrisFlyer service, the innovative seating, and the outstanding wine selection make every journey special. The crew anticipated our needs before we even asked. My preferred airline for long haul.',                        'positive', 10),
('FB007', 'FL007', 'Grace Park',          '2026-03-26', 'JAL economy from Tokyo to LA had a 35-minute delay due to air traffic. The crew apologized and distributed snacks promptly. The seats were comfortable and the entertainment system had excellent Japanese and international content. Delay was frustrating but crew were professional.',      'neutral',   7),
('FB008', 'FL009', 'Henry Foster',        '2026-03-28', 'Qatar Airways business class from Doha was exceptional. The Qsuite privacy panels and the fully flat bed with a real mattress made a long-haul flight actually enjoyable. The food and wine selection were outstanding. Highly recommended.',                                                 'positive',  9),
('FB009', 'FL010', 'Isabella Cruz',       '2026-03-29', 'United economy from San Francisco to Tokyo was adequate. The seat was acceptable but the service felt rushed. In-flight wifi was very slow and expensive. The aircraft was clean and boarding was efficient. A functional but uninspiring experience.',                                        'neutral',   6),
('FB010', 'FL011', 'James Wong',          '2026-03-30', 'Cathay Pacific business class was excellent. The seat converts to a full flat bed and the duvet was genuinely cozy. The crew were attentive and warm. The Hong Kong hub is very efficient for connections. A consistently reliable and premium airline.',                                      'positive',  8),
('FB011', 'FL012', 'Karen Davis',         '2026-03-20', 'Delta domestic JFK to LAX was smooth and punctual. For a 5-hour flight the economy seats were acceptable. The snack options were limited but the overall experience was professional and hassle-free. Good value for a domestic route.',                                                       'neutral',   7),
('FB012', 'FL013', 'Lukas Mueller',       '2026-03-21', 'Lufthansa premium economy Munich to Singapore had great seat comfort and reasonable food. The service was polite but not as attentive as business class. A good middle ground for long haul when business class prices are prohibitive.',                                                      'positive',  8),
('FB013', 'FL014', 'Maria Santos',        '2026-03-22', 'Emirates economy Dubai to Sydney was surprisingly good. The entertainment system had hundreds of movies and the seat had a USB charger and decent recline. Food portions were generous for economy. Would recommend Emirates economy for long haul.',                                           'positive',  8),
('FB014', 'FL015', 'Nathan Black',        '2026-03-23', 'British Airways business class had a 2-hour delay due to technical issues. While the seat and food were excellent once airborne, the communication from gate staff about the delay was poor. A significant disappointment for a premium long-haul ticket.',                                   'negative',  5),
('FB015', 'FL001', 'Olivia White',        '2026-03-24', 'Delta economy across the Atlantic was uncomfortable. The seat pitch was very tight and the person in front reclined fully for the entire 7-hour flight. The food was passable and the crew were friendly despite a very busy cabin. Would not choose Delta economy transatlantic again.',     'negative',  5),
('FB016', 'FL003', 'Patrick O''Brien',    '2026-03-25', 'British Airways economy from London to New York is solid value. The seat had a personal screen and USB port. The food was decent for economy class. Arrived 15 minutes early which is always a bonus. A reliable and comfortable choice.',                                                   'positive',  8),
('FB017', 'FL006', 'Rachel Nguyen',       '2026-03-26', 'Singapore Airlines is my gold standard for long haul travel. The business class cabin on the Singapore-London route is exceptionally comfortable. The crew remembered my dietary preferences from a previous flight — a wonderful personal touch that no other airline has matched.',         'positive', 10),
('FB018', 'FL008', 'Sebastian Koch',      '2026-03-27', 'Air France economy Paris to Tokyo sold out very quickly and I barely secured a seat. The flight itself was good with attentive service and reasonable food. The entertainment content in both French and Japanese was a thoughtful plus for the route.',                                       'positive',  8),
('FB019', 'FL009', 'Tanya Patel',         '2026-03-28', 'Qatar Airways Doha to New York had some turbulence but the crew handled it with complete professionalism. Business class food was excellent and the Qsuite offered exceptional privacy. The Hamad International Airport connection experience was world-class.',                              'positive',  9),
('FB020', 'FL005', 'Uma Johansson',       '2026-03-29', 'Lufthansa premium economy from Frankfurt left 40 minutes late due to a late arriving aircraft. Once airborne the service was attentive and the food noticeably better than standard economy. The delay spoiled what was otherwise a good flight experience.',                                 'neutral',   6);

-- ============================================================================
-- 7. STAGE FOR SEMANTIC MODELS
-- ============================================================================

CREATE STAGE IF NOT EXISTS TRAVEL_DEMO.BOOKING.BOOKING_MODELS
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = 'Stores Cortex Analyst semantic model YAML files for hotels and flights';

-- After running this script, upload the semantic model YAMLs from the setup/ directory:
--
--   snow stage copy setup/hotels_semantic.yaml  @TRAVEL_DEMO.BOOKING.BOOKING_MODELS --connection $SNOW_CONNECTION
--   snow stage copy setup/flights_semantic.yaml @TRAVEL_DEMO.BOOKING.BOOKING_MODELS --connection $SNOW_CONNECTION
--
-- Verify upload:
--   LIST @TRAVEL_DEMO.BOOKING.BOOKING_MODELS;

-- ============================================================================
-- 8. CORTEX SEARCH SERVICES
-- ============================================================================

CREATE OR REPLACE CORTEX SEARCH SERVICE TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS_SEARCH
    ON REVIEW_TEXT
    ATTRIBUTES HOTEL_ID, GUEST_NAME, REVIEW_DATE, SENTIMENT, RATING
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            REVIEW_ID,
            HOTEL_ID,
            GUEST_NAME,
            REVIEW_DATE,
            REVIEW_TEXT,
            SENTIMENT,
            RATING
        FROM TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS
    );

CREATE OR REPLACE CORTEX SEARCH SERVICE TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK_SEARCH
    ON FEEDBACK_TEXT
    ATTRIBUTES FLIGHT_ID, PASSENGER_NAME, FEEDBACK_DATE, SENTIMENT, RATING
    WAREHOUSE = COMPUTE_WH
    TARGET_LAG = '1 hour'
    AS (
        SELECT
            FEEDBACK_ID,
            FLIGHT_ID,
            PASSENGER_NAME,
            FEEDBACK_DATE,
            FEEDBACK_TEXT,
            SENTIMENT,
            RATING
        FROM TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK
    );

-- ============================================================================
-- 9. CORTEX AGENTS
-- ============================================================================

CREATE OR REPLACE AGENT TRAVEL_DEMO.BOOKING.HOTELS_BOOKING_AGENT
FROM SPECIFICATION $$
{
  "models": {"orchestration": "claude-4-sonnet"},
  "orchestration": {"budget": {"seconds": 60, "tokens": 16000}},
  "instructions": {
    "system": "You are a Senior Hotel Concierge at TravelDemo, a premium travel booking platform. Your role is to help guests discover and book the perfect hotel from our global portfolio.\n\nAnswer questions about hotel availability, pricing, amenities, guest ratings, room types, cancellation policies, and loyalty tiers.\n\nROUTING LOGIC:\n- For pricing, availability counts, rating averages, room counts, or any quantitative queries about hotels: use cortex_analyst\n- For guest reviews, sentiment, qualitative feedback, or what guests are saying about a hotel: use cortex_search\n- For comprehensive hotel questions: use both tools — cortex_analyst for the data, cortex_search for guest context\n\nBe conversational, warm, and precise. Provide recommendations when helpful.",
    "orchestration": "- For pricing, availability, rating averages, room counts, or any numerical queries about hotels: use cortex_analyst\n- For guest reviews, sentiment, or qualitative hotel feedback: use cortex_search\n- For comprehensive hotel questions: use both tools",
    "response": "Be concise and helpful. Format prices clearly (e.g. $450/night). When listing hotels, use a brief bullet or table format. Always include star rating, price, and availability when discussing specific properties."
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "cortex_analyst",
        "description": "Use this tool to query the HOTELS table for structured data: pricing, availability counts, star ratings, room types, cancellation policies, loyalty tiers, and booking status across our hotel portfolio."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "cortex_search",
        "description": "Use this tool to search guest reviews for qualitative feedback, sentiment, common praises or complaints, and what guests are actually saying about specific hotels or amenities."
      }
    }
  ],
  "tool_resources": {
    "cortex_analyst": {
      "semantic_model_file": "@TRAVEL_DEMO.BOOKING.BOOKING_MODELS/hotels_semantic.yaml",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "COMPUTE_WH"
      }
    },
    "cortex_search": {
      "name": "TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS_SEARCH",
      "max_results": 5
    }
  }
}
$$;

CREATE OR REPLACE AGENT TRAVEL_DEMO.BOOKING.FLIGHTS_BOOKING_AGENT
FROM SPECIFICATION $$
{
  "models": {"orchestration": "claude-4-sonnet"},
  "orchestration": {"budget": {"seconds": 60, "tokens": 16000}},
  "instructions": {
    "system": "You are a Senior Flight Booking Specialist at TravelDemo. Your role is to help travelers find and book the ideal flight for their journey.\n\nAnswer questions about flight availability, fares, schedules, seat classes, airlines, routes, delays, and passenger experiences across our global flight inventory.\n\nROUTING LOGIC:\n- For fares, seat counts, delay averages, route comparisons, or any quantitative queries about flights: use cortex_analyst\n- For passenger reviews, feedback, qualitative airline information, or what passengers are saying: use cortex_search\n- For comprehensive questions about an airline or route: use both tools — cortex_analyst for the data, cortex_search for passenger context\n\nBe conversational, informative, and precise. Highlight value and relevant trade-offs between options.",
    "orchestration": "- For fares, available seats, delay averages, duration, or any numerical queries about flights: use cortex_analyst\n- For passenger reviews, feedback, or qualitative airline information: use cortex_search\n- For comprehensive airline or route questions: use both tools",
    "response": "Be concise and helpful. Format prices clearly (e.g. $380 economy). When listing flights, include airline, route, seat class, price, and availability. Highlight notable trade-offs (e.g. price vs. comfort)."
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "cortex_analyst",
        "description": "Use this tool to query the FLIGHTS table for structured data: fares by route and class, available seats, delay statistics, flight durations, airline comparisons, and booking status."
      }
    },
    {
      "tool_spec": {
        "type": "cortex_search",
        "name": "cortex_search",
        "description": "Use this tool to search passenger feedback for qualitative information, sentiment, common praises or complaints, and what travelers are saying about specific airlines, routes, or seat classes."
      }
    }
  ],
  "tool_resources": {
    "cortex_analyst": {
      "semantic_model_file": "@TRAVEL_DEMO.BOOKING.BOOKING_MODELS/flights_semantic.yaml",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "COMPUTE_WH"
      }
    },
    "cortex_search": {
      "name": "TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK_SEARCH",
      "max_results": 5
    }
  }
}
$$;

-- ============================================================================
-- VERIFICATION
-- ============================================================================

-- Confirm tables and row counts
SELECT 'HOTELS'        AS tbl, COUNT(*) AS rows FROM TRAVEL_DEMO.BOOKING.HOTELS
UNION ALL
SELECT 'HOTEL_REVIEWS' AS tbl, COUNT(*) AS rows FROM TRAVEL_DEMO.BOOKING.HOTEL_REVIEWS
UNION ALL
SELECT 'FLIGHTS'       AS tbl, COUNT(*) AS rows FROM TRAVEL_DEMO.BOOKING.FLIGHTS
UNION ALL
SELECT 'FLIGHT_FEEDBACK' AS tbl, COUNT(*) AS rows FROM TRAVEL_DEMO.BOOKING.FLIGHT_FEEDBACK;

-- Confirm agents were created
SHOW AGENTS IN SCHEMA TRAVEL_DEMO.BOOKING;

-- Confirm search services
SHOW CORTEX SEARCH SERVICES IN SCHEMA TRAVEL_DEMO.BOOKING;
