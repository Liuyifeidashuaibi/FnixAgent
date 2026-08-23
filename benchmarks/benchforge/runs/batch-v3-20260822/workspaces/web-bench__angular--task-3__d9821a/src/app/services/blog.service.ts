import { Injectable } from '@angular/core';
import { Blog } from '../models/blog.model';

@Injectable({
  providedIn: 'root'
})
export class BlogService {
  private blogs: Blog[] = [
    {
      id: '1',
      title: 'Morning',
      date: '2024-01-15',
      excerpt: 'Embracing the beauty of early morning hours',
      content: `# Morning

There is something truly magical about the early morning hours. As the world slowly awakens, the soft golden light filters through the curtains, painting the room in warm hues.

## The Quiet Hours

The morning offers a rare gift — silence. Before the rush of the day begins, there is a moment of pure tranquility. The birds begin their gentle chorus, and the air feels crisp and refreshing.

## A Time for Reflection

Many great minds throughout history have cherished the morning as a time for deep thinking and creativity. It is during these quiet hours that we can set our intentions, plan our day, and find clarity in our thoughts.

## Making the Most of Mornings

- Wake up a little earlier each day
- Enjoy a warm cup of coffee or tea
- Spend a few minutes in meditation or journaling
- Take a short walk to greet the sunrise

The morning is not just a time of day — it is a mindset. Embrace it, and let it set the tone for everything that follows.`,
      author: 'Sarah Chen',
      category: 'Lifestyle'
    },
    {
      id: '2',
      title: 'The Art of Minimalism',
      date: '2024-01-20',
      excerpt: 'Finding freedom through simplicity',
      content: `# The Art of Minimalism

Minimalism is more than a design aesthetic — it is a way of life that focuses on what truly matters.

## Less is More

In a world that constantly pushes us to accumulate more, minimalism offers a refreshing alternative. By intentionally choosing to own fewer things, we create space for experiences, relationships, and personal growth.

## Getting Started

1. Start with one room or one category
2. Ask yourself: Does this add value to my life?
3. Let go of items you no longer use or love
4. Focus on quality over quantity

## The Benefits

Living minimally can reduce stress, save money, and help you discover what you truly value. It is not about deprivation — it is about making room for what matters most.`,
      author: 'James Park',
      category: 'Design'
    },
    {
      id: '3',
      title: 'Digital Detox',
      date: '2024-02-01',
      excerpt: 'Reclaiming your time in a connected world',
      content: `# Digital Detox

In our hyper-connected world, taking a break from technology has become essential for mental well-being.

## Why We Need a Detox

Constant notifications, endless scrolling, and screen time can lead to burnout, anxiety, and decreased productivity. A digital detox helps reset our relationship with technology.

## Tips for a Successful Detox

- Set specific screen-free hours each day
- Turn off non-essential notifications
- Replace screen time with offline hobbies
- Designate tech-free zones in your home

## The Results

After just a few days of reduced screen time, many people report better sleep, improved focus, and a greater sense of presence in their daily lives.`,
      author: 'Emma Wilson',
      category: 'Wellness'
    },
    {
      id: '4',
      title: 'Creative Coding',
      date: '2024-02-10',
      excerpt: 'Where logic meets imagination',
      content: `# Creative Coding

Creative coding is the intersection of programming and artistic expression — where algorithms become art.

## What is Creative Coding?

Unlike traditional programming focused on solving business problems, creative coding uses code as a medium for artistic expression. It encompasses generative art, interactive installations, and visual experiments.

## Getting Started

You don't need to be an expert programmer to start. Tools like p5.js, Processing, and Three.js make it accessible to beginners while offering depth for experienced developers.

## The Joy of Creative Coding

There is something deeply satisfying about watching your code come to life as visual art. It reminds us that programming is not just a technical skill — it is a creative one.`,
      author: 'Alex Rivera',
      category: 'Technology'
    },
    {
      id: '5',
      title: 'Sustainable Living',
      date: '2024-02-18',
      excerpt: 'Small changes, big impact',
      content: `# Sustainable Living

Sustainable living is about making conscious choices that reduce our environmental footprint without sacrificing quality of life.

## Everyday Changes

- Reduce single-use plastics
- Choose local and seasonal produce
- Conserve water and energy
- Support sustainable brands

## The Ripple Effect

When we make sustainable choices, we influence those around us. Small actions compound over time, creating meaningful change for our planet.

## It Starts Today

You don't need to change everything overnight. Start with one habit, master it, then add another. The journey to sustainable living is a marathon, not a sprint.`,
      author: 'Maria Santos',
      category: 'Environment'
    }
  ];

  getBlogs(): Blog[] {
    return this.blogs;
  }

  getBlogById(id: string): Blog | undefined {
    return this.blogs.find(blog => blog.id === id);
  }

  getDefaultBlog(): Blog | undefined {
    return this.blogs.find(blog => blog.title === 'Morning');
  }
}
