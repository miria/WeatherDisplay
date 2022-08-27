import codecs
import configparser
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

import cairosvg
import pygame
import webcolors


class Forecast:
    """Container class for individual forecasts"""
    condition_id = -1
    condition_text = 'N/A'
    condition_time = 'general'
    humidity = -1
    precip_chance = -1
    temp = -1
    timestamp = -1


class Weather:
    """Container class for current weather conditions"""
    condition_id = -1
    condition_text = 'N/A'
    condition_time = 'general'
    hourly_precip = 0  # measured in mm
    humidity = -1
    temp = -1
    timezone = -1
    wind_speed = -1
    wind_dir = "N/A"


def get_rgb(color):
    """Tries to generate a (red, green, blue) tuple from a hex value or color name string.
       If an appropriate value cannot be parsed, the program is terminated."""
    try:
        return webcolors.hex_to_rgb(color)
    except:
        pass

    try:
        return webcolors.name_to_rgb(color)
    except:
        pass

    print("Unknown color ", color)
    sys.exit(1)


def get_hex(color):
    """Tries to generate a hex value string from a partial hex value or color name string.
       If an appropriate value cannot be parsed, the program is terminated."""
    try:
        return webcolors.normalize_hex(color)
    except:
        pass

    try:
        return webcolors.name_to_hex(color)
    except:
        pass

    print("Unknown color ", color)
    sys.exit(1)


class WeatherDataDisplay:
    """Generates a small weather display to a local interface"""
    _last_refresh = 0
    _screen = None
    _background = None
    _weather_icon_sprite = None
    _weather_temp_sprite = None
    _humidity_icon_sprite = None
    _weather_humidity_sprite = None
    _precip_icon_sprite = None
    _weather_precip_sprite = None
    _wind_icon_sprite = None
    _weather_wind_sprite = None
    _forecast_sprites = []
    _last_update_sprite = None
    _internet_status_sprite = None
    _all_sprites = None

    def __init__(self, config):
        self._config = config
        self._data_fetcher = WeatherDataFetcher(config)
        self._image_selector = WeatherImageSelector(config)
        self._formatter = WeatherFormatter(config)

    def run(self):
        if config_data.getboolean('display', 'print_only'):
            self.print_display()
            return
        self._init_display()

        done = False
        while not done:
            pygame.time.wait(5000)
            for event in pygame.event.get():
                if event == pygame.QUIT:
                    done = True
            self._update_display()

    def _init_display(self):
        width = self._config.getint('display', 'width')
        height = self._config.getint('display', 'height')
        border = self._config.getint('display', 'border')
        color = self._config.get('display', 'foreground_color', fallback='black')
        font = self._config.get('display', 'font', fallback='arial')
        font_size = self._config.getint('display', 'font_size', fallback=10)

        pygame.init()
        pygame.mouse.set_visible(False)
        self._screen = pygame.display.set_mode((width, height), pygame.NOFRAME)
        self._background = pygame.Surface((width, height))
        self._background.convert()
        self._background.fill(get_rgb(self._config.get('display', 'background_color', fallback='white')))

        # Divide the screen into segments on a 12 x 9 grid, as shown below:
        #
        #  -- -- -- -- -- -- -- -- -- -- -- --
        # |        |              | 3 |   4    | 1. Weather Icon
        #                           -- -- -- --  2. Temperature
        # |   1    |      2       | 5 |   6   |  3. Humidity Icon
        #                          -- -- -- --   4. Humidity
        # |        |              | 7 |   8   |  5. Precipitation Icon
        #  -- -- -- -- -- -- -- -- -- -- -- --   6. Precipitation
        # |    9   |   10   |   11   |   12   |  7. Wind Speed Icon
        #  -- -- -- -- -- -- -- -- -- -- -- --   8. Wind Speed
        # |        |        |        |        |  9-12. Forecast Date
        # |   13   |   14   |   15   |   16   |  13-16. Forecast Icon
        #  -- -- -- -- -- -- -- -- -- -- -- --   17-20. Forecast Temp
        # |   17   |   18   |   19   |   20   |  21-24. Forecast Precip Chance (plus icon)
        #  -- -- -- -- -- -- -- -- -- -- -- --   25. Last Updated
        # |  |  21 |  |  22 |  | 23  |  | 24  |  26. Connection Status
        #  -- -- -- -- -- -- -- -- -- -- -- --
        # |            22            |   23   |
        #  -- -- -- -- -- -- -- -- -- -- -- --

        width_unit = round((width - border * 2) / 12.0)
        height_unit = round((height - border * 2) / 9.0)
        self._all_sprites = pygame.sprite.Group()

        # Weather icon display
        self._weather_icon_sprite = WeatherIconSprite(self._image_selector, width_unit * 3, height_unit * 3, color,
                                                      border,
                                                      border)
        self._all_sprites.add(self._weather_icon_sprite)

        # Temperature display
        self._weather_temp_sprite = TextSprite(font, font_size * 2, color, width_unit * 5, height_unit * 3,
                                               width_unit * 3 + border, border)
        self._all_sprites.add(self._weather_temp_sprite)

        # Humidity display
        self._humidity_icon_sprite = IconSprite(self._image_selector.get_icon("humidity"), width_unit, height_unit,
                                                color, width_unit * 8 + border,
                                                border)
        self._all_sprites.add(self._humidity_icon_sprite)
        self._weather_humidity_sprite = TextSprite(font, font_size, color, width_unit * 3, height_unit,
                                                   width_unit * 9 + border, border + border, False)
        self._all_sprites.add(self._weather_humidity_sprite)

        # Hourly precipitation display
        self._precip_icon_sprite = IconSprite(self._image_selector.get_icon("precipitation"), width_unit, height_unit,
                                              color, width_unit * 8 + border,
                                              height_unit + border)
        self._all_sprites.add(self._precip_icon_sprite)
        self._weather_precip_sprite = TextSprite(font, font_size, color, width_unit * 3, height_unit,
                                                 width_unit * 9 + border, height_unit + border, False)
        self._all_sprites.add(self._weather_precip_sprite)

        # Wind speed display
        self._wind_icon_sprite = IconSprite(self._image_selector.get_icon("wind"), width_unit, height_unit, color,
                                            width_unit * 8 + border,
                                            height_unit * 2 + border)
        self._all_sprites.add(self._wind_icon_sprite)
        self._weather_wind_sprite = TextSprite(font, font_size, color, width_unit * 3, height_unit,
                                               width_unit * 9 + border, height_unit * 2 + border, False)
        self._all_sprites.add(self._weather_wind_sprite)

        # Display the next four 3-hourly forecasts.
        for i in range(4):
            # Time display
            forecast_date_sprite = TextSprite(font, font_size, color, width_unit * 3, height_unit * 1,
                                              i * (width_unit * 3) + border, height_unit * 3 + border)
            self._all_sprites.add(forecast_date_sprite)

            # Forecast icon display
            weather_icon_sprite = WeatherIconSprite(self._image_selector, width_unit * 3, height_unit * 2, color,
                                                    i * (width_unit * 3) + border, height_unit * 4 + border)
            self._all_sprites.add(weather_icon_sprite)

            # Forecast temperature display
            forecast_temp_sprite = TextSprite(font, font_size, color, width_unit * 3, height_unit * 1,
                                              i * (width_unit * 3) + border, height_unit * 6 + border)
            self._all_sprites.add(forecast_temp_sprite)

            # Precipitation chance display
            precip_chance_icon_sprite = IconSprite(self._image_selector.get_icon("precipitation_chance"), width_unit,
                                                   height_unit, color,
                                                   i * (width_unit * 3) + border,
                                                   height_unit * 7 + border)
            self._all_sprites.add(precip_chance_icon_sprite)
            forecast_precip_sprite = TextSprite(font, font_size, color, width_unit * 2, height_unit * 1,
                                                i * (width_unit * 3) + width_unit + border, height_unit * 7 + border,
                                                False)
            self._all_sprites.add(forecast_precip_sprite)

            self._forecast_sprites.append(
                [forecast_date_sprite, weather_icon_sprite, forecast_temp_sprite, precip_chance_icon_sprite,
                 forecast_precip_sprite])

        # Last updated timestamp display
        self._last_update_sprite = TextSprite(font, font_size - 2, color, width_unit * 9, height_unit * 1, border,
                                              height_unit * 8 + border)
        self._all_sprites.add(self._last_update_sprite)

        # Internet status display
        self._internet_status_sprite = TextSprite(font, font_size + 2, "red", width_unit * 3, height_unit * 1,
                                                  (width_unit * 9) + border, height_unit * 8 + border)
        self._all_sprites.add(self._internet_status_sprite)
        self._update_display()

    def _update_display(self):
        """Updates the display sprites to reflect the most recent weather data and forecast."""
        self._data_fetcher.update_data()

        self._internet_status_sprite.update_text("OK" if self._data_fetcher.internet_active else "DOWN")
        self._internet_status_sprite.update_color("green" if self._data_fetcher.internet_active else "red")

        if self._data_fetcher.last_weather_update > self._last_refresh:
            self._last_update_sprite.update_text(
                "Last Update: " + self._formatter.format_datetime(self._data_fetcher.last_weather_update))

            weather = self._data_fetcher.weather
            if weather is not None:
                self._weather_icon_sprite.update_condition(weather.condition_id, weather.condition_time)
                self._weather_temp_sprite.update_text(self._formatter.format_temp(weather.temp, ""))
                self._weather_humidity_sprite.update_text(self._formatter.format_percentage(weather.humidity))
                self._weather_precip_sprite.update_text(self._formatter.format_precip(weather.hourly_precip))
                self._weather_wind_sprite.update_text(
                    self._formatter.format_wind_speed(weather.wind_speed, weather.wind_dir))

                forecasts = self._data_fetcher.forecasts
                if forecasts is not None:
                    for i in range(4):
                        self._forecast_sprites[i][0].update_text(self._formatter.format_time(forecasts[i].timestamp))
                        self._forecast_sprites[i][1].update_condition(forecasts[i].condition_id,
                                                                      forecasts[i].condition_time)
                        self._forecast_sprites[i][2].update_text(self._formatter.format_temp(forecasts[i].temp))
                        self._forecast_sprites[i][4].update_text(
                            self._formatter.format_percentage(forecasts[i].precip_chance))
                self._last_refresh = self._data_fetcher.last_weather_update
            print("Display data updated.")

        self._all_sprites.clear(self._screen, self._background)
        self._all_sprites.draw(self._screen)
        pygame.display.flip()

    def print_display(self):
        """Prints the current weather data and forecast to the console."""
        self._data_fetcher.update_data()

        print("Internet Status: %s" % ("OK" if self._data_fetcher.internet_active else "DOWN"))
        last_update = self._data_fetcher.last_weather_update
        if last_update > 0:
            weather = self._data_fetcher.weather
            forecasts = self._data_fetcher.forecasts
            print("Last weather update: %s " %
                  (self._formatter.format_datetime(last_update)))
            print("------Current Conditions------")
            print(self._formatter.format_weather(weather))
            print("Condition: %s" % weather.condition_text)
            print("------Forecast---------")

            for forecast in forecasts:
                print("------ %s:-------" %
                      (self._formatter.format_datetime(forecast.timestamp + weather.timezone)))
                print(self._formatter.format_forecast(forecast))
                print("C: %s" % forecast.condition_text)
        else:
            print("Unable to fetch weather data.")


class IconSprite(pygame.sprite.Sprite):
    """Sprite class for displaying icons"""

    def __init__(self, icon_path, width, height, color, x_pos, y_pos):
        super().__init__()
        self._icon_path = icon_path
        self._width = width
        self._height = height
        self._color = color
        self._x_pos = x_pos
        self._y_pos = y_pos
        self._load_image()

    def _get_path(self):
        return self._icon_path

    def _load_image(self):
        image = pygame.image.load(self._get_path())
        min_side = min(self._width, self._height)
        image = pygame.transform.scale(image, (min_side, min_side))
        self.image = pygame.Surface((self._width, self._height))
        # Center the resized icon in the space
        self.image.blit(image, [int(self._width / 2 - min_side / 2),
                                int(self._height / 2 - min_side / 2)])
        self.rect = self.image.get_rect()
        self.rect.x = self._x_pos
        self.rect.y = self._y_pos

    def update(self):
        self._load_image()


class WeatherIconSprite(IconSprite):
    """Sprite class for selecting and displaying weather icons"""

    def __init__(self, image_selector, width, height, color, x_pos, y_pos):
        self._image_selector = image_selector
        self._condition_id = -1
        self._condition_time = ''
        super(WeatherIconSprite, self).__init__(image_selector.get_unknown_image(), width, height, color, x_pos, y_pos)

    def _get_path(self):
        return self._image_selector.get_image(self._condition_id, self._condition_time)

    def update_condition(self, condition_id, condition_time):
        self._condition_id = condition_id
        self._condition_time = condition_time
        self._load_image()


class TextSprite(pygame.sprite.Sprite):
    """Sprite class for displaying text"""

    def __init__(self, font, size, color, width, height, x_pos, y_pos, center=True):
        super().__init__()
        self._font = pygame.font.SysFont(font, size)
        self._color = color
        self._width = width
        self._height = height
        self._x_pos = x_pos
        self._y_pos = y_pos
        self._text = "N/A"
        self._center = center

    def _load_text(self):
        self.textSurf = self._font.render(self._text, 1, get_rgb(self._color))
        self.image = pygame.Surface((self._width, self._height))
        # Center the text image in the space
        self.image.blit(self.textSurf, [int(self._width / 2 - self.textSurf.get_width() / 2) if self._center else 0,
                                        int(self._height / 2 - self.textSurf.get_height() / 2)])
        self.rect = self.image.get_rect()
        self.rect.x = self._x_pos
        self.rect.y = self._y_pos

    def update_text(self, text):
        self._text = text
        self._load_text()

    def update_color(self, color):
        self._color = color
        self._load_text()

    def update(self):
        self._load_text()


class WeatherFormatter:
    """Class for formatting weather data for display"""

    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

    def __init__(self, config):
        self._time_format = config['location']['time_format']
        self._date_format = config['location']['date_format']
        self._units = config['location']['units']
        self.temp_unit = "°K"
        self.wind_unit = "m/s"
        if self._units == "metric":
            self._temp_unit = "°C"
        elif self._units == "imperial":
            self._temp_unit = "°F"
            self._wind_unit = "mph"

    def format_wind_speed(self, speed, degree, label=""):
        # Find the closest cardinal direction for the 16 wind directions defined.
        index = round(degree / (360.0 / len(self.directions)))
        return "%s %d %s %s" % (label, speed, self._wind_unit, self.directions[(index % 16)])

    def format_temp(self, temp, label=""):
        return "%s %d %s" % (label, temp, self._temp_unit)

    def format_percentage(self, humidity, label=""):
        return "%s %d%%" % (label, humidity)

    def format_precip(self, precip, label=""):
        if self._units == "imperial":
            # Convert to inches for imperial.
            return "%s %0.2f in/h" % (label, precip * 0.0393700787)
        return "%s %d mm/h" % (label, precip)

    def format_weather(self, weather):
        return (self.format_temp(weather.temp, "Temp:") + "\n" +
                self.format_percentage(weather.humidity, "Humidity:") + "\n" +
                self.format_precip(weather.hourly_precip, "Precip:") + "\n" +
                self.format_wind_speed(weather.wind_speed, weather.wind_dir, "Wind: "))

    def format_forecast(self, forecast):
        return (self.format_temp(forecast.temp, "T:") + "\n" +
                self.format_percentage(forecast.humidity, "H:") + "\n" +
                self.format_percentage((forecast.precip_chance * 100), "P:"))

    def format_datetime(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime(self._date_format)

    def format_time(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime(self._time_format)


class WeatherImageSelector:
    """Stores weather image mappings and fetches the correct image based on the weather"""
    _image_mappings = {}

    def __init__(self, config):
        self._image_dir = config['icons']['image_dir']
        self._mapping_file = config['icons']['mapping_file']
        self._image_set = config['icons']['image_set']
        self._color = config['icons']['image_color']
        self._svg_dir = config.get('icons', 'svg_dir', fallback=None)
        self._init_images()

    def _init_images(self):
        print("Starting image initialization.")
        if self._image_set not in ['light', 'dark', 'custom']:
            print("Invalid image_set value - choose light, dark, or custom")
            sys.exit(1)

        path = os.path.join(self._image_dir, self._image_set)
        if self._image_set == 'custom':
            # Custom color images are generated from base SVG images. Check that the SVG
            # image directory exists.
            self._color = get_hex(self._color)
            dir_name = self._color
            if not os.path.exists(self._svg_dir):
                print("Invalid path for SVG images: ", self._svg_dir)
                sys.exit(1)
            path = os.path.join(self._image_dir, dir_name)
            if not os.path.exists(path):
                os.mkdir(path)
                print("Created image dir ", path)
        elif self._is_image_dir(path):
            print("Invalid image directory ", self._image_dir)
            sys.exit(1)
        self._image_dir = path

        mappings = {}
        try:
            # Load the condition code/time of day to image filename mappings.
            handler = open(self._mapping_file, 'r')
            for line in handler.readlines():
                pieces = line.strip().split(',')
                weather_id = int(pieces[0])
                if weather_id not in mappings:
                    mappings[weather_id] = {}
                mappings[weather_id][pieces[1].strip()] = pieces[2].strip()
        except Exception as e:
            print("Invalid image mapping file: %s" % e)
            sys.exit(1)
        self._image_mappings = mappings

        print("Images initialized.")
        self._initialized = True

    def _is_image_dir(self, path):
        return os.path.exists(path) and len([f for f in os.listdir(path) if f.endswith(".png")]) > 0

    def has_image(self, condition_id, condition_time):
        if not self._initialized:
            return False
        if condition_id not in self._image_mappings:
            return False
        condition_map = self._image_mappings[condition_id]
        if condition_time not in condition_map and 'general' not in condition_map:
            return False
        return True

    def _maybe_generate_custom_image(self, path, filename):
        if self._image_set == 'custom' and not os.path.exists(path):
            # Convert the SVG image to a PNG image in the requested color and store it in the color's image directory.
            with codecs.open(os.path.join(self._svg_dir, filename.replace(".png", ".svg")), encoding='utf-8',
                             errors='ignore') as f:
                content = f.read()
                old_style = 'style="'
                new_style = 'style="fill:%s;stroke:%s;' % (self._color, self._color)
                new_svg = content.replace(old_style, new_style)
                cairosvg.svg2png(bytestring=new_svg, write_to=os.path.join(self._image_dir, filename),
                                 output_width=300, output_height=300)

    def get_image(self, condition_id, condition_time):
        if not self._initialized:
            return None
        if not self.has_image(condition_id, condition_time):
            return self.get_unknown_image()
        path = os.path.join(self._image_dir, self._image_mappings[condition_id][condition_time])
        self._maybe_generate_custom_image(path, self._image_mappings[condition_id][condition_time])
        return path

    def get_icon(self, name):
        filename = "wi-na.png"
        if name == "humidity":
            filename = "wi-humidity.png"
        elif name == "precipitation":
            filename = "wi-raindrops.png"
        elif name == "wind":
            filename = "wi-strong-wind.png"
        elif name == "precipitation_chance":
            filename = "wi-umbrella.png"

        path = os.path.join(self._image_dir, filename)
        self._maybe_generate_custom_image(path, filename)
        return path

    def get_unknown_image(self):
        path = os.path.join(self._image_dir, "wi-na.png")
        self._maybe_generate_custom_image(path, "wi-na.png")
        return path


class WeatherDataFetcher:
    """Fetches data from the weather API and parses it for processing."""

    weather = None
    forecasts = None
    last_weather_update = -1
    internet_active = False

    def __init__(self, config):
        params = {
            'latitude': config['location']['latitude'],
            'longitude': config['location']['longitude'],
            'key': config['weather_api']['key'],
            'units': config['location']['units'],
        }
        self._weather_url = config['weather_api']['weather_url'].format(**params)
        self._forecast_url = config['weather_api']['forecast_url'].format(**params)
        self._poll_interval_seconds = config.getint('weather_api', 'poll_interval_seconds')
        self._last_weather_fetch = 0

    def _fetch_url(self, url):
        try:
            handler = urllib.request.urlopen(url)
            return json.loads(handler.read())
        except Exception as e:
            print("Error fetching URL:", e)
            return None

    def _fetch_weather(self):
        self._last_weather_fetch = time.time()
        weather = None
        forecasts = None

        # Fetch the current weather.
        weather_data = self._fetch_url(self._weather_url)
        if weather_data is not None:
            weather = self._parse_current_weather(weather_data)

        # Fetch the forecast.
        forecast_data = self._fetch_url(self._forecast_url)
        if forecast_data is not None:
            forecasts = self._parse_forecasts(forecast_data)

        # Only update the data if both are present.
        if forecasts and weather:
            self.weather = weather
            self.forecasts = forecasts
            self.last_weather_update = time.time()
            print("Weather data updated.")

    def _parse_condition_time(self, icon_label):
        if icon_label[-1] == 'd': return 'day'
        if icon_label[-1] == 'n': return 'night'
        return 'general'

    def _parse_forecasts(self, json_data):
        try:
            forecasts = []
            for forecast_data in json_data['list']:
                forecast = Forecast()
                forecast.condition_id = forecast_data['weather'][0]['id']
                forecast.condition_text = forecast_data['weather'][0]['description']
                forecast.condition_time = self._parse_condition_time(forecast_data['weather'][0]['icon'])
                forecast.humidity = forecast_data['main']['humidity']
                forecast.precip_chance = forecast_data['pop'] * 100
                forecast.temp = forecast_data['main']['temp']
                forecast.timestamp = forecast_data['dt']
                forecasts.append(forecast)
            return forecasts
        except Exception as e:
            print("Error parsing forecasts: ", e)
            return None

    def _parse_current_weather(self, json_data):
        try:
            weather = Weather()
            weather.condition_id = json_data['weather'][0]['id']
            weather.condition_text = json_data['weather'][0]['description']
            weather.condition_time = self._parse_condition_time(json_data['weather'][0]['icon'])
            weather.humidity = json_data['main']['humidity']
            weather.temp = json_data['main']['temp']
            weather.timezone = json_data['timezone']
            weather.wind_dir = json_data['wind']['deg']
            weather.wind_speed = json_data['wind']['speed']

            if 'rain' in json_data:
                weather.hourly_precip += json_data['rain']['1h']
            if 'snow' in json_data:
                weather.hourly_precip += json_data['snow']['1h']
            return weather
        except Exception as e:
            print("Error parsing current weather: ", e)
            return None

    def _fetch_internet_status(self):
        try:
            urllib.request.urlopen('http://google.com')
            self.internet_active = True
        except Exception as e:
            print("Error fetching internet status: ", e)
            self.internet_active = False

    def update_data(self):
        self._fetch_internet_status()
        if self.internet_active and (time.time() > self._last_weather_fetch + self._poll_interval_seconds):
            self._fetch_weather()


if __name__ == '__main__':
    config_data = configparser.ConfigParser()
    if not len(sys.argv) == 2:
        print("Usage: weather_display.py config_file")
        sys.exit(1)
    config_data.read_file(open(sys.argv[1]))
    display = WeatherDataDisplay(config_data)
    display.run()
